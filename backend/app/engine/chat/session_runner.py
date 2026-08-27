from __future__ import annotations

from collections.abc import AsyncIterator

from app.engine.agent.events import done, error_event, text_delta, think_delta
from app.engine.agent.prompts import MODE_DEFAULT, MODE_FORCE_WRITE, MODE_NO_WRITE
from app.engine.chat.sse import parse_agent_sse_event
from app.engine.chat.turn_hub import TurnExecutionHub
from app.engine.chat.turn_inject import PendingInject, TurnInjectBroker
from app.engine.knowledge_writer import is_markdown_path
from app.engine.enabled_skills import SkillCatalogEntry


class ChatSessionRunner:
    """HTTP 侧薄 facade：持久回合委托 TurnExecutionHub；ephemeral 直跑 agent。"""

    def __init__(
        self,
        agent,
        conversations,
        inject_broker: TurnInjectBroker | None = None,
        turn_hub: TurnExecutionHub | None = None,
        *,
        enabled_skills=None,
    ):
        self.agent = agent
        self.conversations = conversations
        self.enabled_skills = enabled_skills
        self.inject_broker = inject_broker or TurnInjectBroker()
        self.turn_hub = turn_hub or TurnExecutionHub(
            agent, conversations, inject_broker=self.inject_broker
        )
        if turn_hub is not None:
            self.inject_broker = self.turn_hub.inject_broker

    def resolve_skill_catalog(
        self, skill_catalog: list[SkillCatalogEntry] | None = None
    ) -> list[SkillCatalogEntry]:
        """启用集 → catalog；HTTP 只经此入口，勿直接摸 EnabledSkillsStore。"""
        if skill_catalog is not None:
            return list(skill_catalog)
        if self.enabled_skills is None:
            return []
        return self.enabled_skills.catalog_for_chat(self.agent.tools.repo)

    def enqueue_inject(self, conversation_id: str, item: PendingInject) -> str:
        return self.turn_hub.enqueue_inject(conversation_id, item)

    def request_stop(self, conversation_id: str) -> bool:
        return self.turn_hub.request_stop(conversation_id)

    def resolve_active_turn_status(self, conversation_id: str) -> dict:
        """Lightweight reconcile probe: DB turn row + in-memory observability."""
        meta = self.conversations.get_active_turn_meta(conversation_id)
        turn_id = meta.get("turn_id")
        db_status = meta.get("status")
        if not turn_id:
            return {
                "conversation_id": conversation_id,
                "turn_id": None,
                "status": None,
                "started_at": None,
                "last_seq": None,
                "observable": False,
            }
        active = self.turn_hub.get_active(conversation_id)
        observable = (
            active is not None
            and active.get("turn_id") == turn_id
            and not active.get("finished")
        )
        if db_status == "running":
            status = "running" if observable else "orphaned"
        else:
            status = db_status
        last_seq = None
        if active is not None and active.get("turn_id") == turn_id:
            last_seq = active.get("seq")
        return {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "status": status,
            "started_at": meta.get("started_at"),
            "last_seq": last_seq,
            "observable": observable,
        }

    def begin_persisted_turn(
        self,
        *,
        conversation_id: str,
        user_text: str,
        client_message_id: str,
        observation_allowed: bool,
        doc_context: list | None,
        primary_doc: str | None,
        attachments: list | None,
        doc_paths: list[str],
        skill_catalog: list[dict[str, str]] | None = None,
        web_enabled: bool,
        reuse_user_message_id: str | None = None,
    ) -> dict:
        catalog = self.resolve_skill_catalog(skill_catalog)
        return self.turn_hub.begin_and_ensure(
            conversation_id=conversation_id,
            user_text=user_text,
            client_message_id=client_message_id,
            observation_allowed=observation_allowed,
            doc_context=doc_context,
            primary_doc=primary_doc,
            attachments=attachments,
            doc_paths=doc_paths,
            skill_catalog=catalog,
            web_enabled=web_enabled,
            reuse_user_message_id=reuse_user_message_id,
        )

    async def stream_ephemeral(
        self,
        text: str,
        *,
        doc_paths: list[str],
        skill_catalog: list[dict[str, str]] | None = None,
        primary_doc: str | None,
        web_enabled: bool,
    ) -> AsyncIterator[str]:
        catalog = self.resolve_skill_catalog(skill_catalog)
        try:
            async for ev in self.agent.run(
                text,
                mode=MODE_DEFAULT,
                active_doc_path=primary_doc,
                active_doc_paths=doc_paths,
                primary_doc_path=primary_doc,
                skill_catalog=catalog,
                history=None,
                conversation_id=None,
                web_enabled=web_enabled,
            ):
                yield ev
        except Exception as e:
            yield error_event(str(e))

    async def replay_turn(self, turn: dict) -> AsyncIterator[str]:
        assistant = turn.get("assistant_message") or {}
        for block in assistant.get("timeline") or []:
            if block.get("type") == "think" and block.get("content"):
                yield think_delta(block["content"])
            elif block.get("type") == "text" and block.get("content"):
                yield text_delta(block["content"])
        yield done(assistant.get("sources") or [], assistant.get("total_duration_ms") or 0)

    async def observe_turn(
        self,
        conversation_id: str,
        turn_id: str,
        *,
        after_seq: int = 0,
    ) -> AsyncIterator[str]:
        async for ev in self.turn_hub.subscribe(
            conversation_id, turn_id, after_seq=after_seq
        ):
            yield ev

    async def observe_active_turn(
        self,
        conversation_id: str,
        *,
        after_seq: int = 0,
    ) -> AsyncIterator[str]:
        turn_id = self.turn_hub.resolve_turn_id(conversation_id)
        if not turn_id:
            return
        async for ev in self.turn_hub.subscribe(
            conversation_id, turn_id, after_seq=after_seq
        ):
            yield ev


def ingest_from_write_doc_result(data: dict) -> dict:
    status = data.get("status")
    rel_path = data.get("rel_path")
    if not rel_path:
        sources = data.get("sources") or []
        rel_path = sources[0]["path"] if sources and sources[0].get("path") else None
    if status is None:
        status = "saved" if rel_path else "rejected"
    return {
        "status": status,
        "rel_path": rel_path,
        "question_id": data.get("question_id"),
        "message": data.get("summary", ""),
    }


async def consume_agent_ingest(agent, text: str) -> dict:
    result: dict | None = None
    async for ev in agent.run(text, mode=MODE_FORCE_WRITE):
        parsed = parse_agent_sse_event(ev)
        if not parsed:
            continue
        event_type, data = parsed
        if event_type == "tool_result" and data.get("tool") == "write_doc":
            result = ingest_from_write_doc_result(data)
    if result is None:
        raise RuntimeError("Agent 未调用 write_doc")
    return result


async def consume_agent_ask(agent, query: str) -> dict:
    text_parts: list[str] = []
    sources: list[dict] = []
    async for ev in agent.run(query, mode=MODE_NO_WRITE):
        parsed = parse_agent_sse_event(ev)
        if not parsed:
            continue
        event_type, data = parsed
        if event_type == "text_delta":
            text_parts.append(data.get("delta", ""))
        elif event_type == "done":
            sources = data.get("sources") or []
    attachments = [
        s["path"]
        for s in sources
        if s.get("type") == "kb"
        and s.get("path")
        and not is_markdown_path(s["path"])
    ]
    return {"text": "".join(text_parts), "sources": sources, "attachments": attachments}
