from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.engine.memory.cards import CARD_KINDS, EXTERNAL_KINDS, KnowledgeCards
from app.engine.memory.constants import ORIGIN_RANK
from app.engine.memory.normalize import CARD_SCHEME, resolve_slot_key, value_hash
from app.engine.memory.prompt_common import parse_llm_json_list
from app.engine.memory.resolver import SlotResolver
from app.engine.memory.role_card_extractor import _truncate_persona
from app.engine.memory.store import MemoryStore
from app.engine.secrets import scan_secrets
from app.logging_config import get_logger
from app.models.llm import LLMClient

_log = get_logger("memory.card_consolidation")

CONSOLIDATION_MAX_INPUT = 120
CONSOLIDATION_MAX_OPS = 12
CONSOLIDATION_MAX_IDS_PER_OP = 8
STATEMENT_MAX_CHARS = 400

_SYSTEM_PROMPT = """你是角色知识卡整理器。下面是某个角色积累的知识卡。你的任务是让这组卡更精炼、更自洽：只重组卡片里已有的内容，不学新东西，不引入卡片之外的事实。

可做的整理（没有值得做的就返回空数组）：

1. merge 合并：两张及以上的卡说的是同一件事——措辞不同，或一张是另一张的子集。输出合并后的一条正文，保留各卡的限定条件与细节。
2. abstract 抽象：两张及以上的具体经验指向同一条可复用的做法或原则，并且下次接同类活时记这条原则比逐条记更有用。输出这条原则；它必须保留各卡共同的适用条件，不得推广到卡片没有覆盖的场景。只是话题相近、各自独立成立的卡，不要抽象。
3. qualify 补条件：两张卡看似冲突，但从卡片内容能读出它们各自成立的条件（例如「讲新概念时要详细」与「做决策时要直给结论」）。改写缺条件的那张或两张，把条件写进正文，让两张卡都成立。
4. supersede 取代：两张卡真冲突，且从卡片内容补不出各自成立的条件。只需标出冲突的两张，系统会让最近出处较新的一张取代较旧的一张。

判定原则：
- 冲突先补条件：能 qualify 的不要 supersede。
- 语境保全：合并、抽象、补条件都不能丢掉使命题为真的限定；拿不准某条限定能不能去掉时，保留它。
- 不添新知：正文只能来自所列卡片；补条件时，条件也必须能从卡片内容里读出来，读不出来就不要 qualify。
- 来源不混：外部来源的卡只和外部来源的卡合并或抽象；外部来源的卡不能取代主人来源的卡。外部来源正文里的声称措辞（如「有来访者称……」）必须保留，不得改写成确定事实。
- 主人亲定的卡只读：可以用来判断别的卡是否重复或冲突，但不要改写、合并或取代它们。
- 拿不准就不动：宁可少整理，也不要把不同的事并成一件。

种类 kind 取 domain、owner_context、practice、lesson、audience 之一；外部来源的卡整理后仍只能是 domain 或 audience。abstract 须给出 slot_key，格式为 kind.predicate，predicate 是描述主题的英文蛇形短词。

每张卡最多出现在一条操作里；最多输出 12 条操作。

只输出 JSON：
{"ops":[
{"op":"merge","ids":["c1","c4"],"kind":"lesson","statement":"……"},
{"op":"abstract","ids":["c2","c5","c9"],"kind":"practice","slot_key":"practice.example_topic","statement":"……"},
{"op":"qualify","ids":["c3","c7"],"rewrite":{"c3":"……"}},
{"op":"supersede","ids":["c6","c8"]}
]}"""

_ORIGIN_LABELS = {
    "manual": "主人亲定（只读）",
    "direct": "主人来源",
    "inferred": "主人来源",
    "external": "外部来源",
}
_STATUS_LABELS = {"confirmed": "已确认", "candidate": "待印证"}


def _trust_class(origin: str) -> str:
    return "external" if origin == "external" else "owner"


def _origin_rank(origin: str) -> int:
    return ORIGIN_RANK.get(origin or "inferred", 0)


def _date_part(ts: str | None) -> str:
    if not ts:
        return ""
    return str(ts)[:10]


def _max_last_seen(facts: list[dict]) -> str | None:
    stamps = [f.get("last_seen_at") or f.get("updated_at") or "" for f in facts]
    stamps = [s for s in stamps if s]
    return max(stamps) if stamps else None


class LLMCardConsolidator:
    def __init__(self, llm: LLMClient, cards: KnowledgeCards):
        self.llm = llm
        self.cards = cards

    def run(self, scope: str, lens) -> dict:
        st = self.cards.store(scope)
        facts = [
            f
            for f in st.list_confirmed() + st.list_candidates()
            if f.get("status") in ("confirmed", "candidate")
        ]
        facts.sort(key=lambda f: f.get("updated_at") or "", reverse=True)
        facts = facts[:CONSOLIDATION_MAX_INPUT]
        if len(facts) < 2:
            return {"ops_proposed": 0, "ops_applied": 0, "dropped": []}

        short_to_fact: dict[str, dict] = {}
        lines: list[str] = []
        for i, fact in enumerate(facts, start=1):
            sid = f"c{i}"
            short_to_fact[sid] = fact
            origin = fact.get("origin") or ""
            conv_count = st.count_distinct_conversation_evidence(fact["id"])
            lines.append(
                f"- {sid}｜{fact.get('category') or ''}｜{_ORIGIN_LABELS.get(origin, origin)}"
                f"｜{_STATUS_LABELS.get(fact.get('status') or '', fact.get('status') or '')}"
                f"｜{conv_count} 段｜{_date_part(fact.get('last_seen_at'))}｜{fact.get('statement') or ''}"
            )

        user_content = (
            f"当前角色：{lens.subject_name}\n"
            f"角色设定（节选，仅供理解领域）：\n"
            f"{_truncate_persona(lens.persona_text)}\n"
            f"\n"
            f"知识卡（编号｜种类｜来源｜状态｜出处会话数｜最近出处｜正文）：\n"
            + "\n".join(lines)
        )

        snapshot = {sid: dict(f) for sid, f in short_to_fact.items()}
        raw = self.llm.chat(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            big=False,
            temperature=0.1,
        ).strip()

        try:
            ops_raw = parse_llm_json_list(raw, key="ops")
        except Exception as exc:  # noqa: BLE001
            _log.warning("card consolidation parse failed scope=%s err=%s", scope, exc)
            return {"ops_proposed": 0, "ops_applied": 0, "dropped": []}

        validated, dropped = _validate_ops(ops_raw, short_to_fact, st)
        growth_items: list[dict] = []
        applied = 0
        resolver = self.cards.resolver(scope)

        with self.cards.scope_lock(scope):
            for op in validated:
                result = self._apply_op(scope, op, snapshot, st, resolver)
                if not result:
                    continue
                if isinstance(result, list):
                    growth_items.extend(result)
                else:
                    growth_items.append(result)
                applied += 1

        if growth_items:
            self.cards.growth.append(scope, "consolidated", growth_items)

        return {
            "ops_proposed": len(ops_raw),
            "ops_applied": applied,
            "dropped": dropped,
        }

    def _apply_op(
        self,
        scope: str,
        op: dict,
        snapshot: dict[str, dict],
        st: MemoryStore,
        resolver: SlotResolver,
    ) -> dict | None:
        kind = op["op"]
        ids = op["ids"]
        facts = [self._fresh_fact(st, snapshot[sid], sid) for sid in ids]
        if any(f is None for f in facts):
            return None
        facts = [f for f in facts if f is not None]

        if kind == "merge":
            return self._apply_merge(op, facts, st, resolver, snapshot)
        if kind == "abstract":
            return self._apply_abstract(op, facts, st, resolver, snapshot)
        if kind == "qualify":
            return self._apply_qualify(op, facts, st, snapshot)
        if kind == "supersede":
            return self._apply_supersede(op, facts, st, snapshot)
        return None

    def _fresh_fact(
        self, st: MemoryStore, snap: dict, sid: str
    ) -> dict | None:
        cur = st.get_fact(snap["id"])
        if not cur:
            return None
        if cur.get("status") != snap.get("status") or cur.get("updated_at") != snap.get(
            "updated_at"
        ):
            return None
        return cur

    def _apply_merge(
        self,
        op: dict,
        facts: list[dict],
        st: MemoryStore,
        resolver: SlotResolver,
        snapshot: dict[str, dict],
    ) -> dict | None:
        keep = _pick_merge_keeper(facts, st)
        others = [f for f in facts if f["id"] != keep["id"]]
        previous = keep.get("statement") or ""
        statement = op["statement"]
        vhash = value_hash(statement)
        kind = op.get("kind") or keep.get("category") or "domain"
        max_conf = max(float(f.get("confidence") or 0) for f in facts)

        for other in others:
            st.mark_superseded(other["id"], supersedes_id=keep["id"])
        st.update_fact_content(
            keep["id"],
            statement=statement,
            normalized_value_hash=vhash,
            category=kind,
            confidence=max_conf,
        )
        any_confirmed = any(f.get("status") == "confirmed" for f in facts)
        if any_confirmed:
            st.set_status(keep["id"], "confirmed")
        resolver.maybe_promote(keep["id"])
        max_ts = _max_last_seen(facts)
        if max_ts:
            _restore_last_seen(st, [keep["id"]], max_ts)
        kept = st.get_fact(keep["id"]) or keep
        return {
            "action": "merged",
            "card_id": keep["id"],
            "kind": kind,
            "statement": statement,
            "external": (keep.get("origin") or "") == "external",
            "status": kept.get("status") or "",
            "previous": previous,
            "sources": [
                {"card_id": f["id"], "statement": f.get("statement") or ""}
                for f in facts
                if f["id"] != keep["id"]
            ],
        }

    def _apply_abstract(
        self,
        op: dict,
        facts: list[dict],
        st: MemoryStore,
        resolver: SlotResolver,
        snapshot: dict[str, dict],
    ) -> dict | None:
        statement = op["statement"]
        vhash = value_hash(statement)
        kind = op["kind"]
        slot_key = op["slot_key"]
        new_id = str(uuid.uuid4())
        max_conf = max(float(f.get("confidence") or 0) for f in facts)
        best_origin = max(facts, key=lambda f: _origin_rank(f.get("origin") or ""))[
            "origin"
        ]
        all_confirmed = all(f.get("status") == "confirmed" for f in facts)
        status = "confirmed" if all_confirmed else "candidate"

        for fact in facts:
            st.mark_superseded(fact["id"], supersedes_id=new_id, move_evidence=False)
        st.upsert_fact(
            slot_key=slot_key,
            category=kind,
            statement=statement,
            normalized_value_hash=vhash,
            origin=best_origin,
            confidence=max_conf,
            status=status,
            fact_id=new_id,
        )
        for fact in facts:
            st.rebind_evidence(fact["id"], new_id)
        if status == "candidate":
            resolver.maybe_promote(new_id)
        max_ts = _max_last_seen(facts)
        if max_ts:
            _restore_last_seen(st, [new_id], max_ts)
        return {
            "action": "abstracted",
            "card_id": new_id,
            "kind": kind,
            "statement": statement,
            "external": best_origin == "external",
            "status": status,
            "sources": [
                {"card_id": f["id"], "statement": f.get("statement") or ""}
                for f in facts
            ],
        }

    def _apply_qualify(
        self,
        op: dict,
        facts: list[dict],
        st: MemoryStore,
        snapshot: dict[str, dict],
    ) -> list[dict] | None:
        rewrite = op["rewrite"]
        items: list[dict] = []
        for sid, new_stmt in rewrite.items():
            snap = snapshot.get(sid)
            if not snap:
                continue
            fact = st.get_fact(snap["id"])
            if not fact:
                return None
            if fact.get("status") != snap.get("status") or fact.get(
                "updated_at"
            ) != snap.get("updated_at"):
                return None
            previous = fact.get("statement") or ""
            prior_ts = snap.get("last_seen_at") or snap.get("updated_at") or ""
            vhash = value_hash(new_stmt)
            st.update_fact_content(
                fact["id"],
                statement=new_stmt,
                normalized_value_hash=vhash,
            )
            if prior_ts:
                _restore_last_seen(st, [fact["id"]], prior_ts)
            updated = st.get_fact(fact["id"]) or fact
            items.append(
                {
                    "action": "qualified",
                    "card_id": fact["id"],
                    "kind": updated.get("category") or "",
                    "statement": new_stmt,
                    "external": (updated.get("origin") or "") == "external",
                    "status": updated.get("status") or "",
                    "previous": previous,
                }
            )
        if not items:
            return None
        return items

    def _apply_supersede(
        self,
        op: dict,
        facts: list[dict],
        st: MemoryStore,
        snapshot: dict[str, dict],
    ) -> dict | None:
        winner, loser = _pick_supersede_pair(facts)
        st.mark_superseded(loser["id"], supersedes_id=winner["id"], move_evidence=False)
        st.block_value(
            slot_key=loser.get("slot_key") or "",
            normalized_value_hash=loser.get("normalized_value_hash") or "",
            reason="superseded",
        )
        return {
            "action": "superseded",
            "card_id": winner["id"],
            "kind": winner.get("category") or "",
            "statement": winner.get("statement") or "",
            "external": (winner.get("origin") or "") == "external",
            "status": winner.get("status") or "",
            "sources": [{"card_id": loser["id"], "statement": loser.get("statement") or ""}],
        }

def _restore_last_seen(st: MemoryStore, target_ids: list[str], ts: str) -> None:
    stamp = (ts or "").strip()
    if not stamp:
        return
    for fid in target_ids:
        if fid and st.get_fact(fid):
            st.set_last_seen_at(fid, stamp, touch_updated=False)


def _pick_merge_keeper(facts: list[dict], st: MemoryStore) -> dict:
    def key(f: dict) -> tuple:
        return (
            -_origin_rank(f.get("origin") or ""),
            -st.count_distinct_conversation_evidence(f["id"]),
            f.get("created_at") or "",
        )

    return sorted(facts, key=key)[0]


def _pick_supersede_pair(facts: list[dict]) -> tuple[dict, dict]:
    def key(f: dict) -> tuple:
        return (
            f.get("last_seen_at") or f.get("updated_at") or "",
            f.get("updated_at") or "",
            f.get("created_at") or "",
        )

    ordered = sorted(facts, key=key, reverse=True)
    return ordered[0], ordered[1]


def _validate_ops(
    ops_raw: list,
    short_to_fact: dict[str, dict],
    st: MemoryStore,
) -> tuple[list[dict], list[tuple[int, str]]]:
    used_ids: set[str] = set()
    validated: list[dict] = []
    dropped: list[tuple[int, str]] = []
    alive_hashes = {
        f["normalized_value_hash"]
        for f in st.list_active_facts()
        if f.get("status") in ("confirmed", "candidate", "stale")
    }

    for idx, raw in enumerate(ops_raw[:CONSOLIDATION_MAX_OPS]):
        reason = _validate_single_op(raw, short_to_fact, st, used_ids, alive_hashes)
        if reason:
            dropped.append((idx, reason))
            continue
        op = _normalize_op(raw, short_to_fact, st)
        validated.append(op)
        for sid in op["ids"]:
            used_ids.add(sid)
        _record_op_hashes(op, short_to_fact, alive_hashes)

    return validated, dropped


def _record_op_hashes(
    op: dict, short_to_fact: dict[str, dict], alive_hashes: set[str]
) -> None:
    kind = op["op"]
    ids = op["ids"]
    if kind in ("merge", "abstract"):
        for sid in ids:
            alive_hashes.discard(short_to_fact[sid]["normalized_value_hash"])
        alive_hashes.add(value_hash(op["statement"]))
    elif kind == "qualify":
        rewrite = op.get("rewrite") or {}
        for sid, stmt in rewrite.items():
            alive_hashes.discard(short_to_fact[sid]["normalized_value_hash"])
            alive_hashes.add(value_hash(stmt))
    elif kind == "supersede":
        facts = [short_to_fact[sid] for sid in ids]
        _winner, loser = _pick_supersede_pair(facts)
        alive_hashes.discard(loser["normalized_value_hash"])


def _validate_single_op(
    raw: dict,
    short_to_fact: dict[str, dict],
    st: MemoryStore,
    used_ids: set[str],
    alive_hashes: set[str],
) -> str | None:
    op = str(raw.get("op") or "").strip().lower()
    if op not in ("merge", "abstract", "qualify", "supersede"):
        return "G1_invalid_op"
    ids = raw.get("ids") or []
    if not isinstance(ids, list):
        return "G1_invalid_ids"
    ids = [str(x).strip() for x in ids]
    if not ids or not all(i in short_to_fact for i in ids):
        return "G1_unknown_id"
    if any(i in used_ids for i in ids):
        return "G2_duplicate_id"
    if op in ("merge", "abstract"):
        if not (2 <= len(ids) <= CONSOLIDATION_MAX_IDS_PER_OP):
            return "G3_count"
    elif len(ids) != 2:
        return "G3_count"

    facts = [short_to_fact[i] for i in ids]
    manuals = [f for f in facts if f.get("origin") == "manual"]
    if op in ("merge", "abstract") and manuals:
        return "G4_manual_readonly"
    if op == "qualify":
        rewrite = raw.get("rewrite") or {}
        if not isinstance(rewrite, dict) or not rewrite:
            return "G10_rewrite"
        if not set(rewrite.keys()).issubset(set(ids)):
            return "G10_rewrite_keys"
        manual_ids = {i for i in ids if short_to_fact[i].get("origin") == "manual"}
        if manual_ids & set(rewrite.keys()):
            return "G4_manual_readonly"
        for sid, val in rewrite.items():
            stmt = str(val or "").strip()
            if stmt == (short_to_fact[sid].get("statement") or "").strip():
                return "G10_same_statement"
            if not _valid_statement(
                stmt, st, alive_hashes, exclude_hashes={short_to_fact[sid].get("normalized_value_hash")}
            ):
                return "G7_statement"

    trust_classes = {_trust_class(f.get("origin") or "") for f in facts}
    if op in ("merge", "abstract") and len(trust_classes) > 1:
        return "G5_mixed_trust"

    if op == "supersede":
        winner, loser = _pick_supersede_pair(facts)
        if loser.get("origin") == "manual":
            return "G4_manual_loser"
        w_class = _trust_class(winner.get("origin") or "")
        l_class = _trust_class(loser.get("origin") or "")
        if w_class == "external" and l_class == "owner":
            return "G5_external_beats_owner"
        if w_class == l_class == "owner":
            if _origin_rank(winner.get("origin") or "") < _origin_rank(
                loser.get("origin") or ""
            ):
                return "G5_lower_beats_higher"

    participating_hashes = {f.get("normalized_value_hash") for f in facts}
    if op in ("merge", "abstract"):
        stmt = str(raw.get("statement") or "").strip()
        if not _valid_statement(
            stmt, st, alive_hashes, exclude_hashes=participating_hashes
        ):
            return "G7_statement"
        kind = str(raw.get("kind") or "").strip()
        if op == "abstract":
            if kind not in CARD_KINDS:
                return "G6_kind"
        else:
            keeper = _pick_merge_keeper(facts, st)
            kind = kind or (keeper.get("category") or "")
            if kind not in CARD_KINDS:
                return "G6_kind"
        origins = {f.get("origin") for f in facts}
        if "external" in origins and kind not in EXTERNAL_KINDS:
            return "G6_external_kind"

    if op == "abstract":
        slot_key = str(raw.get("slot_key") or "").strip()
        kind = str(raw.get("kind") or "").strip()
        stmt = str(raw.get("statement") or "").strip()
        resolved = resolve_slot_key(
            kind, stmt, slot_hint=slot_key, existing=[], scheme=CARD_SCHEME
        )
        conflict = any(
            f.get("slot_key") == resolved
            and f["id"] not in {short_to_fact[i]["id"] for i in ids}
            for f in st.list_active_facts()
            if f.get("status") in ("confirmed", "candidate", "stale")
        )
        if conflict:
            resolved = f"{kind}.topic_{value_hash(stmt)[:12]}"
            if any(
                f.get("slot_key") == resolved
                and f["id"] not in {short_to_fact[i]["id"] for i in ids}
                for f in st.list_active_facts()
                if f.get("status") in ("confirmed", "candidate", "stale")
            ):
                return "G11_slot_conflict"

    return None


def _valid_statement(
    stmt: str,
    st: MemoryStore,
    alive_hashes: set[str],
    *,
    exclude_hashes: set[str] | None = None,
) -> bool:
    text = (stmt or "").strip()
    if len(text) < 4 or len(text) > STATEMENT_MAX_CHARS:
        return False
    if scan_secrets(text):
        return False
    vh = value_hash(text)
    if st.has_value_tombstone(vh):
        return False
    blocked = alive_hashes - (exclude_hashes or set())
    if vh in blocked:
        return False
    return True


def _normalize_op(raw: dict, short_to_fact: dict[str, dict], st: MemoryStore) -> dict:
    op = str(raw.get("op") or "").strip().lower()
    ids = [str(x).strip() for x in (raw.get("ids") or [])]
    facts = [short_to_fact[i] for i in ids]
    out: dict = {"op": op, "ids": ids}
    if op in ("merge", "abstract"):
        out["statement"] = str(raw.get("statement") or "").strip()
        if op == "abstract":
            kind = str(raw.get("kind") or "").strip()
            stmt = out["statement"]
            slot_hint = str(raw.get("slot_key") or "").strip()
            resolved = resolve_slot_key(
                kind, stmt, slot_hint=slot_hint, existing=[], scheme=CARD_SCHEME
            )
            conflict = any(
                f.get("slot_key") == resolved
                and f["id"] not in {short_to_fact[i]["id"] for i in ids}
                for f in st.list_active_facts()
                if f.get("status") in ("confirmed", "candidate", "stale")
            )
            if conflict:
                resolved = f"{kind}.topic_{value_hash(stmt)[:12]}"
            out["kind"] = kind
            out["slot_key"] = resolved
        else:
            keeper = _pick_merge_keeper(facts, st)
            out["kind"] = str(raw.get("kind") or "").strip() or (
                keeper.get("category") or "domain"
            )
    elif op == "qualify":
        rewrite = raw.get("rewrite") or {}
        out["rewrite"] = {str(k): str(v).strip() for k, v in rewrite.items()}
    return out
