from __future__ import annotations

from collections.abc import AsyncIterator

from app.engine.agent.events import done, error_event, text_delta, think_delta
from app.engine.agent.prompts import MODE_DEFAULT, MODE_FORCE_WRITE, MODE_NO_WRITE
from app.engine.chat.sse import parse_agent_sse_event
from app.engine.chat.turn_hub import TurnExecutionHub, TurnRunSpec
from app.engine.chat.turn_inject import PendingInject, TurnInjectBroker
from app.engine.knowledge_writer import is_markdown_path


class ChatSessionRunner:
    """Agent 运行与观测通道的 deep module；HTTP 层只做 adapter。

    有 conversation_id 的回合由 TurnExecutionHub 在后台 Task 中执行；
    SSE 仅 subscribe，断开不影响执行。
    """

    def __init__(
        self,
        agent,
        conversations,
        inject_broker: TurnInjectBroker | None = None,
        turn_hub: TurnExecutionHub | None = None,
    ):
        self.agent = agent
        self.conversations = conversations
        self.inject_broker = inject_broker or TurnInjectBroker()
        self.turn_hub = turn_hub or TurnExecutionHub(
            agent, conversations, inject_broker=self.inject_broker
        )
        # Keep broker shared if hub was injected with a different one
        if turn_hub is not None:
            self.inject_broker = self.turn_hub.inject_broker

    def enqueue_inject(self, conversation_id: str, item: PendingInject) -> str:
        """Queue a mid-turn user inject for the active turn. Raises KeyError if none."""
        return self.inject_broker.enqueue(conversation_id, item)

    def request_stop(self, conversation_id: str) -> bool:
        return self.turn_hub.request_stop(conversation_id)

    async def stream_ephemeral(
        self,
        text: str,
        *,
        doc_paths: list[str],
        skill_roots: list[str] | None = None,
        primary_doc: str | None,
        web_enabled: bool,
    ) -> AsyncIterator[str]:
        try:
            async for ev in self.agent.run(
                text,
                mode=MODE_DEFAULT,
                active_doc_path=primary_doc,
                active_doc_paths=doc_paths,
                primary_doc_path=primary_doc,
                skill_roots=skill_roots,
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

    async def stream_and_persist(
        self,
        text: str,
        *,
        conversation_id: str,
        turn: dict,
        history: list[dict],
        doc_paths: list[str],
        skill_roots: list[str] | None = None,
        primary_doc: str | None,
        web_enabled: bool,
    ) -> AsyncIterator[str]:
        """Start (or attach to) background turn execution and observe SSE events."""
        spec = TurnRunSpec(
            text=text,
            history=history,
            doc_paths=doc_paths,
            skill_roots=skill_roots,
            primary_doc=primary_doc,
            web_enabled=web_enabled,
        )
        self.turn_hub.ensure_running(conversation_id, turn, spec)
        async for ev in self.turn_hub.subscribe(
            conversation_id, turn["turn_id"], after_seq=0
        ):
            yield ev

    async def observe_active_turn(
        self,
        conversation_id: str,
        *,
        after_seq: int = 0,
    ) -> AsyncIterator[str]:
        """Observe the in-memory active (or retained) turn without starting a new one."""
        turn_id = self.turn_hub.resolve_turn_id(conversation_id)
        if not turn_id:
            return
        async for ev in self.turn_hub.subscribe(
            conversation_id, turn_id, after_seq=after_seq
        ):
            yield ev


def ingest_from_write_kb_result(data: dict) -> dict:
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
        if event_type == "tool_result" and data.get("tool") == "write_kb":
            result = ingest_from_write_kb_result(data)
    if result is None:
        raise RuntimeError("Agent 未调用 write_kb")
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
