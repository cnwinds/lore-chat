"""一次性将旧全文 stem slot 近义事实合并到抽象槽。"""

from __future__ import annotations

import json
from collections import Counter
from typing import Protocol

from app.engine.memory.normalize import is_abstract_slot_key, resolve_slot_key
from app.engine.memory.predicates import get_seed, seed_slot_keys
from app.engine.memory.prompt_common import OWNER_MEMORY_GATE, passes_owner_surface_gate
from app.engine.memory.resolver import SlotAction, SlotResolver
from app.engine.memory.store import MemoryStore
from app.logging_config import get_logger


def _parse_migrate_json(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}

_MIGRATE_SYSTEM = f"""你是记忆槽位迁移助手。把多条关于同一主人的近义/冲突事实归到抽象 slot，并给出 canonical statement。

{OWNER_MEMORY_GATE}

规则：
1. slot_key 必须是 category.predicate 英文蛇形；优先复用种子与已有槽；禁止把整句当 predicate。
2. 同槽近义合并为一条更完整的 statement（第一人称）。
3. 无关或非主人画像的条目跳过（不要放入 groups）。

只输出 JSON：
{{"groups":[{{"slot_key":"preference.illustration_style","category":"preference","statement":"我…","fact_ids":["id1","id2"]}}],"new_predicates":[{{"slot_key":"preference.foo","reason":"…"}}]}}"""


class MigrateLLM(Protocol):
    def chat(self, messages: list[dict], **kwargs) -> str: ...


def _target_slot(fact: dict, *, existing: list[dict]) -> str:
    stmt = fact.get("statement") or ""
    cat = fact.get("category") or "preference"
    current = fact.get("slot_key") or ""
    hint = current if is_abstract_slot_key(current) else None
    return resolve_slot_key(cat, stmt, slot_hint=hint, existing=existing)


def _collect_new_predicate_candidates(groups: dict[str, list[dict]]) -> list[dict]:
    """步骤 5：稳定新谓词候选（非种子、出现 ≥1 次的抽象槽）。"""
    seeds = set(seed_slot_keys())
    counts = Counter(slot for slot in groups)
    out: list[dict] = []
    for slot, n in counts.most_common():
        if slot in seeds or not is_abstract_slot_key(slot):
            continue
        if get_seed(slot):
            continue
        sample = (groups[slot][0].get("statement") or "")[:80]
        is_topic = ".topic_" in slot
        out.append(
            {
                "slot_key": slot,
                "fact_count": n,
                "sample_statement": sample,
                # 非 topic_ 指纹槽、或多次出现 → 建议升格种子
                "suggest_seed": (not is_topic) or n >= 2,
            }
        )
    return out


def _apply_groups(
    store: MemoryStore,
    groups: dict[str, list[dict]],
    *,
    dry_run: bool,
) -> tuple[int, list[str]]:
    resolver = SlotResolver(store)
    merged = 0
    log: list[str] = []
    for slot, items in groups.items():
        if len(items) < 2 and items[0]["slot_key"] == slot:
            continue
        items_sorted = sorted(
            items, key=lambda x: len(x.get("statement") or ""), reverse=True
        )
        primary = items_sorted[0]
        log.append(
            f"{slot}: keep {primary['id'][:8]} ({len(items)} facts) "
            f"stmt={primary['statement'][:60]}"
        )
        if dry_run:
            merged += max(0, len(items) - 1)
            continue
        out = resolver.apply(
            SlotAction(
                slot_key=slot,
                action="merge",
                statement=primary["statement"],
                category=primary.get("category") or "preference",
                origin=primary.get("origin") or "direct",
                confidence=float(primary.get("confidence") or 0.9),
            )
        )
        if not out.get("ok"):
            continue
        new_id = (out.get("fact") or {}).get("id")
        for other in items:
            if new_id and other["id"] != new_id:
                store.mark_superseded(other["id"], supersedes_id=new_id)
                merged += 1
    return merged, log


def _heuristic_groups(facts: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    align_view: list[dict] = []
    for f in facts:
        slot = _target_slot(f, existing=align_view)
        groups.setdefault(slot, []).append(f)
        align_view.append(
            {
                "slot_key": slot,
                "statement": f.get("statement"),
                "category": f.get("category"),
            }
        )
    return groups


def _llm_refine_groups(
    facts: list[dict],
    heuristic: dict[str, list[dict]],
    llm: MigrateLLM,
) -> tuple[dict[str, list[dict]], list[dict]]:
    """对启发式结果调用迁移 LLM，覆盖 slot/canonical；失败则回退启发式。"""
    by_id = {f["id"]: f for f in facts}
    payload_lines = []
    for f in facts[:80]:
        payload_lines.append(
            json.dumps(
                {
                    "id": f["id"],
                    "slot_key": f.get("slot_key"),
                    "category": f.get("category"),
                    "statement": f.get("statement"),
                },
                ensure_ascii=False,
            )
        )
    seed_hint = "种子槽：" + ", ".join(seed_slot_keys()[:40])
    user = (
        seed_hint
        + "\n\n待迁移事实（JSONL）：\n"
        + "\n".join(payload_lines)
        + "\n\n启发式分组仅供参考："
        + json.dumps(
            {k: [x["id"] for x in v] for k, v in list(heuristic.items())[:40]},
            ensure_ascii=False,
        )
    )
    try:
        raw = llm.chat(
            [
                {"role": "system", "content": _MIGRATE_SYSTEM},
                {"role": "user", "content": user},
            ],
            big=False,
            temperature=0.1,
        )
    except Exception as exc:  # noqa: BLE001
        get_logger("memory_migrate").warning("migrate LLM failed: %s", exc)
        return heuristic, []

    data = _parse_migrate_json(raw)
    groups_raw = [x for x in (data.get("groups") or []) if isinstance(x, dict)]
    new_preds = [
        x for x in (data.get("new_predicates") or []) if isinstance(x, dict)
    ]
    if not groups_raw:
        return heuristic, new_preds

    groups: dict[str, list[dict]] = {}
    for g in groups_raw:
        slot = str(g.get("slot_key") or "").strip()
        if not is_abstract_slot_key(slot):
            continue
        ids = g.get("fact_ids") or []
        items = [by_id[i] for i in ids if i in by_id]
        if not items:
            continue
        # 用 LLM canonical 覆盖主 statement（须过主人表面门禁，AGENTS §1.3）
        stmt = str(g.get("statement") or "").strip()
        if stmt and not passes_owner_surface_gate(stmt):
            continue
        if stmt:
            items = sorted(
                items, key=lambda x: len(x.get("statement") or ""), reverse=True
            )
            primary = dict(items[0])
            primary["statement"] = stmt
            if g.get("category"):
                primary["category"] = str(g["category"])
            items = [primary] + items[1:]
        groups.setdefault(slot, []).extend(items)

    # 未出现在 LLM 分组中的事实保留启发式归属
    claimed = {f["id"] for items in groups.values() for f in items}
    for slot, items in heuristic.items():
        for f in items:
            if f["id"] not in claimed:
                groups.setdefault(slot, []).append(f)
    return groups or heuristic, new_preds


def migrate_abstract_slots(
    store: MemoryStore,
    *,
    dry_run: bool = False,
    llm: MigrateLLM | None = None,
) -> dict:
    """扫描 confirmed/candidate，按种子/近义（可选 LLM）对齐并 merge。"""
    facts = sorted(
        store.list_active_facts(),
        key=lambda f: len(f.get("statement") or ""),
        reverse=True,
    )
    groups = _heuristic_groups(facts)
    llm_predicates: list[dict] = []
    used_llm = False
    if llm is not None and facts:
        refined, llm_predicates = _llm_refine_groups(facts, groups, llm)
        # LLM 失败时返回同一 heuristic 对象且无 new_predicates → used_llm=False
        used_llm = refined is not groups or bool(llm_predicates)
        groups = refined

    merged, log = _apply_groups(store, groups, dry_run=dry_run)
    new_predicates = _collect_new_predicate_candidates(groups)
    # 合并 LLM 建议
    seen = {p["slot_key"] for p in new_predicates}
    for p in llm_predicates:
        sk = str(p.get("slot_key") or "")
        if sk and sk not in seen and is_abstract_slot_key(sk) and not get_seed(sk):
            new_predicates.append(
                {
                    "slot_key": sk,
                    "fact_count": 0,
                    "sample_statement": str(p.get("reason") or "")[:80],
                    "suggest_seed": True,
                    "from_llm": True,
                }
            )
            seen.add(sk)

    get_logger("memory_migrate").info(
        "migrate_abstract_slots dry_run=%s groups=%s superseded=%s llm=%s",
        dry_run,
        len(groups),
        merged,
        used_llm,
    )
    return {
        "groups": len(groups),
        "superseded": merged,
        "log": log,
        "dry_run": dry_run,
        "used_llm": used_llm,
        "new_predicates": new_predicates,
    }
