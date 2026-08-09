"""会话级记忆抽取：整段对话（用户为主、助手摘要消歧）→ SlotAction 列表。

生产路径仅 LLM；未配置抽取器或调用失败时不落库，保留 dirty 待下次。
"""

from __future__ import annotations

from typing import Protocol

from app.engine.memory.dialogue_timeline_pack import (
    _compress_messages,
    _normalize_turns,
)

# 兼容：旧测试/调用方可从本模块再导出
from app.engine.memory.dialogue_timeline_pack import (  # noqa: F401
    compress_dialogue_timeline,
    compress_to_self_timeline,
)
from app.engine.memory.normalize import infer_category, resolve_slot_key
from app.engine.memory.predicates import seed_prompt_block
from app.engine.memory.prompt_common import (
    NON_DURABLE_IGNORE,
    OWNER_MEMORY_GATE,
    SCOPE_FIDELITY_GATE,
    parse_llm_json_list,
    passes_owner_surface_gate,
)
from app.engine.memory.resolver import SlotAction
from app.engine.secrets import scan_secrets
from app.models.llm import LLMClient

_MAX_ITEMS = 8

_SYSTEM_PROMPT = f"""你是用户长期记忆抽取器。在「整段会话定稿」后，只提取关于「知识库主人（当前用户）」的稳定画像。

{OWNER_MEMORY_GATE}

{NON_DURABLE_IGNORE}

{SCOPE_FIDELITY_GATE}

规则：
1. 优先复用「已有槽位」与「种子谓词」；只有必要时才 new 新 slot_key（格式 category.predicate，英文蛇形；禁止把整句原文当 predicate）。
2. action：
   - merge：与已有同槽近义，产出更完整 canonical statement
   - replace：真冲突或用户改口（改为/不再/以后）
   - noop：同义复述且无需改句
   - new：该槽尚不存在
3. statement：第一人称、完整、简洁；整理改写时不得删掉使命题为真的限定语；origin=direct（明确自述）或 inferred（推断）。
4. 输入中的 assistant 行仅供指代消歧与限定语境，不得写成主人画像。
5. 无合适事实时返回空数组。

只输出 JSON：
{{"items":[{{"slot_key":"preference.illustration_style","action":"merge","statement":"我…","category":"preference","origin":"direct","confidence":0.9}}]}}"""


class SessionMemoryExtractor(Protocol):
    def extract(
        self,
        messages: list[str] | list[tuple[str, str]],
        *,
        confirmed_summary: list[dict],
    ) -> list[SlotAction]: ...


def _to_action(
    *,
    statement: str,
    slot: str,
    category: str,
    action: str,
    origin: str,
    confidence: float,
) -> SlotAction:
    return SlotAction(
        slot_key=slot,
        action=action,
        statement=statement,
        category=category,
        origin=origin,
        confidence=max(0.0, min(1.0, confidence)),
    )


class LLMSessionExtractor:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def extract(
        self,
        messages: list[str] | list[tuple[str, str]],
        *,
        confirmed_summary: list[dict],
    ) -> list[SlotAction]:
        turns = _normalize_turns(messages)  # type: ignore[arg-type]
        if not turns:
            return []
        # 仅跳过含密钥的用户句，勿整段否决同会话其它自述
        safe_turns = [
            (role, text)
            for role, text in turns
            if not (role == "user" and scan_secrets(text))
        ]
        if not any(role == "user" for role, _ in safe_turns):
            return []
        body = _compress_messages(safe_turns)
        confirmed_lines = []
        for f in confirmed_summary[:40]:
            confirmed_lines.append(f"- {f.get('slot_key')}: {f.get('statement')}")
        confirmed_block = (
            "已确认画像（请对齐合并）：\n" + "\n".join(confirmed_lines)
            if confirmed_lines
            else "已确认画像：空"
        )
        user_content = (
            seed_prompt_block()
            + "\n\n"
            + confirmed_block
            + "\n\n对话（按时间；assistant 行仅供消歧）：\n"
            + body
        )
        raw = self.llm.chat(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            big=False,
            temperature=0.1,
        ).strip()
        items = parse_llm_json_list(raw, key="items")[:_MAX_ITEMS]
        # 长句优先，便于同批近义对齐到同一 topic_/种子
        items.sort(key=lambda x: len(str(x.get("statement") or "")), reverse=True)
        batch_existing = [
            {
                "slot_key": f.get("slot_key"),
                "statement": f.get("statement"),
                "category": f.get("category"),
            }
            for f in confirmed_summary
        ]
        actions: list[SlotAction] = []
        for item in items:
            statement = str(item.get("statement", "")).strip()
            if len(statement) < 3 or scan_secrets(statement):
                continue
            if not passes_owner_surface_gate(statement):
                continue
            slot_raw = str(item.get("slot_key") or "").strip()
            category = str(item.get("category") or infer_category(statement)).strip()
            slot = resolve_slot_key(
                category,
                statement,
                slot_hint=slot_raw,
                existing=batch_existing,
            )
            action = str(item.get("action") or "new").strip().lower()
            if action not in ("merge", "replace", "noop", "new"):
                action = "new"
            origin = str(item.get("origin") or "direct").strip()
            if origin not in ("direct", "inferred"):
                origin = "direct"
            try:
                confidence = float(item.get("confidence", 0.9))
            except (TypeError, ValueError):
                confidence = 0.9
            actions.append(
                _to_action(
                    statement=statement,
                    slot=slot,
                    category=category,
                    action=action,
                    origin=origin,
                    confidence=confidence,
                )
            )
            batch_existing.append(
                {
                    "slot_key": slot,
                    "statement": statement,
                    "category": category,
                }
            )
        return actions
