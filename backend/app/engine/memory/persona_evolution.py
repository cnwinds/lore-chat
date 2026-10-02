"""角色人设 LLM 进化器（P2）。"""

from __future__ import annotations

import json
from typing import Callable

from app.engine.memory.cards import CardLens, KnowledgeCards, parse_scope
from app.engine.memory.normalize import value_hash
from app.engine.persona_edits import plan_edits, texts_to_spans, owner_changes
from app.engine.secrets import scan_secrets
from app.engine.background.purpose import llm_purpose
from app.logging_config import get_logger
from app.models.llm import LLMClient

_log = get_logger("memory.persona_evolution")

EVOLUTION_MIN_CONVERSATIONS = 2
EVOLUTION_MAX_CARDS = 40
EVOLUTION_MAX_EDITS = 8
EVOLUTION_MAX_PROPOSALS = 2
OWNER_MEMORY_MAX_ITEMS = 60
PROPOSAL_TITLE_MAX_CHARS = 40
PROPOSAL_REASON_MAX_CHARS = 200
_SKILL_KINDS = frozenset({"practice", "lesson"})
_DOC_KINDS = frozenset({"domain", "practice", "lesson"})

_SYSTEM_PROMPT = """你是角色人设的维护者。下面是某个角色当前的人设，以及主人在多段对话里反复印证过的这个角色的知识卡。你的任务是判断这些稳定下来的认知该放在哪里；需要时对人设做最小的改动，让人设精炼、自洽。

人设与其他各层的分工：
- 人设是这个角色每一轮都带着的「基因」：定位、职责、长期不变的工作方式和领域框架。人设没有出处、不会淡出，写进去就一直生效，直到有人改它。
- 知识卡带出处，会淡出，会被新的对话修正。会随进展变化的认知（当前进度、眼下的弱项、这一阶段的安排）留在卡片里更合适。
- 主人是谁属于【主人记忆】；对所有角色都成立的规矩属于【全局规则】。二者都已经对这个角色生效。

判定原则：
1. 写进人设之前先问：过一段时间，这条会不会不再成立？会，就留在卡片里，不改人设。
2. 每处改动都要指得出依据。新增或改写人设，依据是所列知识卡；删掉人设里的一段，依据可以是知识卡（这段已被推翻），也可以是主人记忆（这段与主人记忆重复）。指不出依据的改动不做：不为措辞、排版或文风改写主人写的文字。
3. 最小改动：只动需要动的句子，其余逐字保留。新内容放进人设里最相关的位置，沿用人设原有的结构和口吻。人设已经表达了卡片的意思，就不要再加。
4. 语境保全：卡片里使命题成立的限定（某类任务、某个阶段、某个条件）写进人设时一并保留。去掉限定就会变成过度概括的，不写进人设。
5. 冲突先补条件：卡片与人设看似冲突时，若能从二者读出各自成立的条件，就把条件写进人设，让两者都成立；读不出条件，才按卡片改写人设。
6. 删重复要完整覆盖：只有一段人设的全部意思都已在主人记忆里时才删这段；部分重叠的，只删重叠的那一句。拿不准就不删。
7. 不写与【全局规则】冲突的内容；与全局规则冲突的卡片留在卡片里。
8. 【主人最近亲手改过的内容】和【主人回退过的改动】是主人的明确意见：前者不要改动，也不要把主人删掉的加回来；后者不要重做。
9. 拿不准就不动：宁可这次不改，也不要把人设改错。没有值得做的改动时 edits 返回空数组。

升格提议（只是提议，主人接受后才会让角色去做）：
- 若干张卡合起来是一套可重复执行的多步流程，照着做需要固定步骤、模板或脚本，写进人设会太长太细：可提议固化为 Skill（target 为 skill）。
- 卡片积累的是主人日后会翻看的资料性内容（清单、对照表、资料目录），而不是角色怎么做事：可提议写成文档（target 为 doc）。
- 其他情况不提议。【已有提议】里用过的卡不要再提。没有就返回空数组。

find 和 after 必须逐字摘自当前人设，并且在人设里只出现一次，摘得足够长以免重复；after 留空表示追加到人设末尾。basis 只能用所列编号：c 开头是知识卡，m 开头是主人记忆；m 只能用于 delete。reason 用一句话写给主人看，说明为什么这样改。最多 8 条 edits、2 条 proposals。

只输出 JSON：
{"edits":[
{"op":"replace","find":"人设里要改写的原文","text":"改写后的文字","basis":["c3"],"reason":"……"},
{"op":"insert","after":"新内容紧跟其后的人设原文","text":"新增的文字","basis":["c1","c4"],"reason":"……"},
{"op":"delete","find":"人设里要删掉的原文","basis":["m2"],"reason":"……"}
],
"proposals":[
{"target":"skill","title":"……","basis":["c5","c6"],"reason":"……"}
]}"""

_USER_TEMPLATE = """当前角色：{subject_name}

当前人设（<<< 与 >>> 之间逐字）：
<<<
{current}
>>>

【主人最近亲手改过的内容】
{owner_lines}

【主人回退过的改动】
{tombstone_lines}

知识卡（编号｜种类｜出处会话数｜正文）：
{card_lines}

【主人记忆】（编号｜正文）：
{memory_lines}

【已有提议】
{proposal_lines}

【全局规则】（只读，仅用来避免冲突）：
{rules}"""


def sample_persona_evolution_user() -> str:
    return _USER_TEMPLATE.format(
        subject_name="示例角色",
        current="示例人设第一段。\n第二行职责说明。",
        owner_lines="（无）",
        tombstone_lines="（无）",
        card_lines="- c1｜practice｜2 段｜示例知识卡正文。",
        memory_lines="（无）",
        proposal_lines="（无）",
        rules="{《戒律》全文运行时注入}",
    )


def _parse_llm_evolution_payload(raw: str) -> tuple[list[dict], list[dict]]:
    from app.engine.memory.prompt_common import MemoryExtractParseError

    text = (raw or "").strip()
    if not text:
        raise MemoryExtractParseError("empty LLM response")
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise MemoryExtractParseError("no JSON object in LLM response")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise MemoryExtractParseError("invalid JSON in LLM response") from exc
    if not isinstance(data, dict):
        raise MemoryExtractParseError("LLM JSON root must be an object")
    edits = data.get("edits")
    proposals = data.get("proposals")
    if not isinstance(edits, list):
        edits = []
    if not isinstance(proposals, list):
        proposals = []
    return [x for x in edits if isinstance(x, dict)], [
        x for x in proposals if isinstance(x, dict)
    ]


def _none_section(text: str) -> str:
    return text if text.strip() else "（无）"


class LLMPersonaEvolver:
    def __init__(
        self,
        llm: LLMClient,
        cards: KnowledgeCards,
        *,
        rules_text: Callable[[], str] = lambda: "",
    ):
        self.llm = llm
        self.cards = cards
        self.rules_text = rules_text

    def eligible_cards(self, scope: str) -> list[dict]:
        st = self.cards.store(scope)
        marks = self.cards.effective_marks(scope)
        out: list[dict] = []
        for fact in st.list_confirmed():
            if not self._is_eligible(fact, st, marks):
                continue
            out.append(fact)
        return out

    def should_run(self, scope: str) -> bool:
        marks = self.cards.effective_marks(scope)
        st = self.cards.store(scope)
        for fact in st.list_confirmed():
            if not self._is_eligible(fact, st, marks):
                continue
            if fact["id"] not in marks:
                return True
        return False

    def run(self, scope: str, lens: CardLens) -> dict:
        kind, sid = parse_scope(scope)

        if kind == "role":
            try:
                role = self.cards.roles.get(sid)
            except KeyError:
                return {"skipped": "no_new_cards"}
            if (role.get("onboarding_status") or "") == "active":
                return {"skipped": "onboarding"}

        if not self.should_run(scope):
            return {"skipped": "no_new_cards"}

        roles = self.cards.roles
        current = roles.get_persona_body(kind, sid)
        st = self.cards.store(scope)
        marks = self.cards.effective_marks(scope)

        unmarked: list[dict] = []
        reviewed: list[dict] = []
        for fact in st.list_confirmed():
            if not self._is_eligible(fact, st, marks):
                continue
            state = marks.get(fact["id"])
            if state == "reviewed":
                reviewed.append(fact)
            elif state is None:
                unmarked.append(fact)

        def _sort_key(f: dict) -> str:
            return f.get("updated_at") or ""

        unmarked.sort(key=_sort_key, reverse=True)
        reviewed.sort(key=_sort_key, reverse=True)
        card_facts = (unmarked + reviewed)[:EVOLUTION_MAX_CARDS]

        card_refs: dict[str, dict] = {}
        card_lines: list[str] = []
        for i, fact in enumerate(card_facts, start=1):
            ref = f"c{i}"
            card_refs[ref] = fact
            origin = fact.get("origin") or ""
            conv = st.count_distinct_conversation_evidence(fact["id"])
            conv_label = "主人亲定" if origin == "manual" else f"{conv} 段"
            card_lines.append(
                f"- {ref}｜{fact.get('category') or ''}｜{conv_label}｜{fact['statement']}"
            )

        memory_facts: list[dict] = []
        memory_refs: dict[str, dict] = {}
        memory_lines: list[str] = []
        if kind == "role":
            memories = sorted(
                self.cards.owner.store.list_confirmed(),
                key=lambda f: f.get("updated_at") or "",
                reverse=True,
            )[:OWNER_MEMORY_MAX_ITEMS]
            for i, fact in enumerate(memories, start=1):
                ref = f"m{i}"
                memory_refs[ref] = fact
                memory_facts.append(fact)
                memory_lines.append(f"- {ref}｜{fact['statement']}")

        base_rev = roles.latest_persona_revision(kind, sid, source="evolution")
        if not base_rev:
            base_rev = roles.earliest_persona_revision(kind, sid)
        if base_rev:
            base_body = base_rev["body"]
            base_revision_id = base_rev["id"]
        else:
            base_body = current
            base_revision_id = None

        oc = owner_changes(base_body, current)
        restored, rejected = self._rollback_tombstones(kind, sid)
        protected_spans = oc.protected_spans + texts_to_spans(current, restored)
        negative_texts = oc.removed_texts + rejected

        existing_proposals = self.cards.persona_state.list_proposals(scope)
        user_content = self._build_user_message(
            lens.subject_name,
            current,
            oc,
            restored,
            rejected,
            card_lines,
            memory_lines,
            existing_proposals,
            card_refs,
        )


        with llm_purpose("persona.evolve"):
            raw = self.llm.chat(
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                big=True,
                temperature=0.1,
            )
        edits_raw, proposals_raw = _parse_llm_evolution_payload(raw)

        card_ref_ids = set(card_refs)
        memory_ref_ids = set(memory_refs)
        plan = plan_edits(
            current,
            edits_raw,
            card_refs=card_ref_ids,
            memory_refs=memory_ref_ids,
            protected_spans=protected_spans,
            negative_texts=negative_texts,
            secret_scan=lambda t: bool(scan_secrets(t)),
            max_edits=EVOLUTION_MAX_EDITS,
        )

        if kind == "persona":
            proposals_valid = []
        else:
            proposals_valid = self._validate_proposals(
                proposals_raw,
                card_ref_ids,
                card_refs,
                existing_proposals,
                accepted_this_run=[],
            )

        edits_proposed = len(edits_raw)
        proposals_added = 0
        revision_id = None

        if plan.applied:
            meta_ops = []
            merged_card_ids: list[str] = []
            for ed in plan.applied:
                basis_meta = []
                for ref in ed.card_refs:
                    fact = card_refs.get(ref)
                    if not fact:
                        continue
                    basis_meta.append(
                        {
                            "ref": ref,
                            "card_id": fact["id"],
                            "statement": fact.get("statement") or "",
                        }
                    )
                    if ed.op in ("replace", "insert"):
                        merged_card_ids.append(fact["id"])
                for ref in ed.memory_refs:
                    fact = memory_refs.get(ref)
                    if not fact:
                        continue
                    basis_meta.append(
                        {
                            "ref": ref,
                            "memory_id": fact["id"],
                            "statement": fact.get("statement") or "",
                        }
                    )
                meta_ops.append(
                    {
                        "op": ed.op,
                        "find": ed.find,
                        "after": ed.after,
                        "text": ed.text,
                        "reason": ed.reason,
                        "basis": basis_meta,
                    }
                )
            meta = {
                "ops": meta_ops,
                "merged_card_ids": sorted(set(merged_card_ids)),
                "base_revision_id": base_revision_id,
            }
            rev = roles.apply_persona_evolution(
                kind,
                sid,
                expected_body=current,
                new_body=plan.body,
                meta=meta,
            )
            if rev is None:
                return {"aborted": "persona_changed"}
            revision_id = rev["id"]
            self._write_marks(
                scope,
                card_facts,
                plan.applied,
                revision_id,
                merged_card_ids=set(merged_card_ids),
            )
            self._append_persona_growth(scope, rev["id"], plan.applied, card_refs, memory_refs)
        else:
            self._write_marks(
                scope,
                card_facts,
                [],
                None,
                merged_card_ids=set(),
            )

        growth_proposal_items: list[dict] = []
        for prop in proposals_valid:
            basis_payload = []
            basis_stmts: list[str] = []
            for ref in prop["basis_refs"]:
                fact = card_refs[ref]
                basis_payload.append(
                    {
                        "card_id": fact["id"],
                        "statement": fact.get("statement") or "",
                    }
                )
                basis_stmts.append(fact.get("statement") or "")
            row = self.cards.persona_state.add_proposal(
                scope,
                target=prop["target"],
                title=prop["title"],
                reason=prop["reason"],
                basis=basis_payload,
            )
            proposals_added += 1
            growth_proposal_items.append(
                {
                    "action": "proposed",
                    "proposal_id": row["id"],
                    "target": prop["target"],
                    "title": prop["title"],
                    "reason": prop["reason"],
                    "basis": basis_stmts,
                    "status": "pending",
                }
            )
        if growth_proposal_items:
            self.cards.growth.append(scope, "proposal", growth_proposal_items)

        return {
            "edits_proposed": edits_proposed,
            "edits_applied": len(plan.applied),
            "proposals_added": proposals_added,
            "revision_id": revision_id,
            "dropped": plan.dropped,
        }

    @staticmethod
    def _is_eligible(fact: dict, st, marks: dict[str, str]) -> bool:
        if fact.get("status") != "confirmed":
            return False
        if (fact.get("origin") or "") == "external":
            return False
        cid = fact["id"]
        state = marks.get(cid)
        if state in ("merged", "rejected"):
            return False
        conv = st.count_distinct_conversation_evidence(cid)
        if conv >= EVOLUTION_MIN_CONVERSATIONS or fact.get("origin") == "manual":
            return True
        return False

    def _rollback_tombstones(
        self, kind: str, sid: str
    ) -> tuple[list[str], list[str]]:
        restored: list[str] = []
        rejected: list[str] = []
        revs = self.cards.roles.list_persona_revisions(kind, sid, limit=500)
        for rev in revs:
            if rev.get("source") != "evolution" or not rev.get("rolled_back_by"):
                continue
            for op in (rev.get("meta") or {}).get("ops") or []:
                if not isinstance(op, dict):
                    continue
                o = op.get("op")
                if o in ("replace", "delete"):
                    find = str(op.get("find") or "")
                    if find.strip():
                        restored.append(find)
                if o in ("replace", "insert"):
                    text = str(op.get("text") or "")
                    if text.strip():
                        rejected.append(text)
        return restored, rejected

    def _build_user_message(
        self,
        subject_name: str,
        current: str,
        oc,
        restored: list[str],
        rejected: list[str],
        card_lines: list[str],
        memory_lines: list[str],
        existing_proposals: list[dict],
        card_refs: dict[str, dict],
    ) -> str:
        owner_parts: list[str] = []
        for t in oc.added_texts:
            owner_parts.append(f"- 加入或改成：「{t.strip()}」")
        for t in oc.removed_texts:
            owner_parts.append(f"- 删掉：「{t.strip()}」")
        owner_lines = _none_section("\n".join(owner_parts))

        tomb_parts: list[str] = []
        for t in restored:
            tomb_parts.append(f"- 恢复了：「{t.strip()}」")
        for t in rejected:
            tomb_parts.append(f"- 不要：「{t.strip()}」")
        tombstone_lines = _none_section("\n".join(tomb_parts))

        proposal_lines_list: list[str] = []
        inv_cards = {v["id"]: k for k, v in card_refs.items()}
        for prop in existing_proposals:
            target = prop.get("target") or "skill"
            title = prop.get("title") or ""
            refs: list[str] = []
            for b in prop.get("basis") or []:
                cid = b.get("card_id") or ""
                if cid in inv_cards:
                    refs.append(inv_cards[cid])
                else:
                    stmt = b.get("statement") or ""
                    if stmt:
                        refs.append(stmt[:20])
            ref_str = "、".join(refs) if refs else "…"
            if target == "skill":
                proposal_lines_list.append(f"- 固化为 Skill「{title}」：{ref_str}")
            else:
                proposal_lines_list.append(f"- 写成文档「{title}」：{ref_str}")
        proposal_lines = _none_section("\n".join(proposal_lines_list))

        rules = self.rules_text() or ""
        rules = _none_section(rules)

        return _USER_TEMPLATE.format(
            subject_name=subject_name,
            current=current,
            owner_lines=owner_lines,
            tombstone_lines=tombstone_lines,
            card_lines=_none_section("\n".join(card_lines)),
            memory_lines=_none_section("\n".join(memory_lines)),
            proposal_lines=proposal_lines,
            rules=rules,
        )

    def _validate_proposals(
        self,
        raw: list[dict],
        card_ref_ids: set[str],
        card_refs: dict[str, dict],
        existing_proposals: list[dict],
        *,
        accepted_this_run: list[dict],
    ) -> list[dict]:
        used_cards: set[str] = set()
        for prop in existing_proposals:
            for b in prop.get("basis") or []:
                cid = b.get("card_id")
                if cid:
                    used_cards.add(cid)

        out: list[dict] = []
        for item in raw:
            if len(out) >= EVOLUTION_MAX_PROPOSALS:
                break
            target = item.get("target")
            if target not in ("skill", "doc"):
                continue
            title = str(item.get("title") or "").strip()
            if not title or len(title) > PROPOSAL_TITLE_MAX_CHARS:
                continue
            reason = str(item.get("reason") or "").strip()
            if not reason or len(reason) > PROPOSAL_REASON_MAX_CHARS:
                continue
            if scan_secrets(title) or scan_secrets(reason):
                continue
            basis_raw = item.get("basis")
            if not isinstance(basis_raw, list) or not basis_raw:
                continue
            basis_refs = [str(x) for x in basis_raw]
            if any(r not in card_ref_ids for r in basis_refs):
                continue
            card_ids = {card_refs[r]["id"] for r in basis_refs}
            if card_ids & used_cards:
                continue
            kinds_ok = _SKILL_KINDS if target == "skill" else _DOC_KINDS
            if any((card_refs[r].get("category") or "") not in kinds_ok for r in basis_refs):
                continue
            out.append(
                {
                    "target": target,
                    "title": title,
                    "reason": reason,
                    "basis_refs": basis_refs,
                }
            )
            used_cards |= card_ids
        return out

    def _write_marks(
        self,
        scope: str,
        card_facts: list[dict],
        applied,
        revision_id: str | None,
        *,
        merged_card_ids: set[str],
    ) -> None:
        applied_card_ids = set(merged_card_ids)
        items: list[tuple[str, str, str, str | None]] = []
        existing = self.cards.persona_state.marks(scope)
        with self.cards.scope_lock(scope):
            for fact in card_facts:
                cid = fact["id"]
                sh = value_hash(fact.get("statement") or "")
                prev = existing.get(cid, {})
                if cid in applied_card_ids:
                    items.append((cid, "merged", sh, revision_id))
                elif prev.get("state") == "merged":
                    continue
                else:
                    items.append((cid, "reviewed", sh, None))
            if items:
                self.cards.persona_state.set_marks(scope, items)

    def _append_persona_growth(
        self,
        scope: str,
        revision_id: str,
        applied,
        card_refs: dict[str, dict],
        memory_refs: dict[str, dict],
    ) -> None:
        items: list[dict] = []
        for ed in applied:
            basis_stmts: list[str] = []
            for ref in ed.card_refs:
                f = card_refs.get(ref)
                if f:
                    basis_stmts.append(f.get("statement") or "")
            for ref in ed.memory_refs:
                f = memory_refs.get(ref)
                if f:
                    basis_stmts.append(f.get("statement") or "")
            before = ed.find if ed.op != "insert" else ""
            after = ed.text if ed.op != "delete" else ""
            items.append(
                {
                    "action": "evolved",
                    "revision_id": revision_id,
                    "op": ed.op,
                    "reason": ed.reason,
                    "before": before,
                    "after": after,
                    "basis": basis_stmts,
                }
            )
        if items:
            self.cards.growth.append(scope, "persona", items)
