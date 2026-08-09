from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator

from app.config import Settings
from app.engine.agent.events import (
    done,
    inject_deferred,
    parallel_batch_end,
    parallel_batch_start,
    text_delta,
    think_delta,
    tool_progress,
    tool_start,
    user_inject,
)
from app.engine.chat.turn_inject import PendingInject, TurnInjectBroker
from app.engine.agent.run_report import AgentRunReport
from app.engine.agent.tool_events import emit_tool_result_sse
from app.engine.agent.tools import (
    READ_ONLY_TOOLS,
    TOOL_LABELS,
    ToolRegistry,
    can_parallelize,
)
from app.engine.agent.tool_progress import ToolProgressExecutor
from app.engine.source_key import extend_sources
from app.engine.usage.context import usage_context
from app.logging_config import get_logger
from app.models.llm import ChatWithToolsResult, LLMClient, ToolCall

_log = get_logger("agent.tool_loop")

_LIMIT_MSG = "（已达工具调用上限，以上为目前能给出的结论。）"
_NON_SERIALIZABLE_KEYS = frozenset({"hits", "ingest_result"})


def tool_awaits_user(out: dict) -> bool:
    """工具结果是否要求本轮停下来等用户（ask_user / sandbox_confirm）。"""
    if out.get("awaiting_user") or out.get("awaiting_confirm"):
        return True
    qid = out.get("question_id")
    options = out.get("options")
    return bool(qid) and isinstance(options, list) and len(options) > 0


class AgentToolLoop:
    """LLM 多轮工具循环与 SSE 事件生成（deep module）；Orchestrator 只做会话上下文 adapter。"""

    def __init__(self, settings: Settings, llm: LLMClient, tools: ToolRegistry):
        self.settings = settings
        self.llm = llm
        self.tools = tools
        self._tool_progress = ToolProgressExecutor(tools.execute)

    async def stream(
        self,
        messages: list[dict],
        *,
        tools_for_run: list[dict],
        conversation_id: str | None,
        active_doc_path: str | None,
        started_at: float | None = None,
        turn_id: str | None = None,
        run_id: str | None = None,
        inject_broker: TurnInjectBroker | None = None,
        on_inject_applied=None,
    ) -> AsyncIterator[str]:
        start = started_at if started_at is not None else time.monotonic()
        run_id = run_id or uuid.uuid4().hex[:8]
        all_sources: list[dict] = []
        tool_call_count = 0
        llm_rounds = 0
        tool_active_doc_path = active_doc_path
        report = AgentRunReport(
            layer="agent",
            stop_reason="unknown",
            conversation_id=conversation_id,
            turn_id=turn_id,
            run_id=run_id,
            tool_limit=self.settings.agent_max_tool_calls,
        )
        _log.info(
            "agent run start cid=%s turn_id=%s run_id=%s tool_limit=%d",
            conversation_id or "-",
            turn_id or "-",
            run_id,
            self.settings.agent_max_tool_calls,
        )

        try:
            while tool_call_count < self.settings.agent_max_tool_calls:
                llm_rounds += 1
                result: ChatWithToolsResult | None = None
                with usage_context(
                    conversation_id=conversation_id, turn_id=turn_id
                ):
                    stream_iter = iter(
                        self.llm.stream_chat_with_tools(
                            messages, tools_for_run, big=True
                        )
                    )
                    sentinel = object()
                    while True:
                        chunk = await asyncio.to_thread(next, stream_iter, sentinel)
                        if chunk is sentinel:
                            break
                        if chunk.think_delta:
                            yield think_delta(chunk.think_delta)
                        if chunk.text_delta:
                            yield text_delta(chunk.text_delta)
                        if chunk.result is not None:
                            result = chunk.result
                if result is None:
                    report.stop_reason = "llm_stream_incomplete"
                    report.detail = f"round={llm_rounds} no ChatWithToolsResult"
                    break
                if not result.content and not result.tool_calls:
                    _log.warning(
                        "agent llm round empty content=%r tool_calls=0 messages=%d round=%d",
                        result.content,
                        len(messages),
                        llm_rounds,
                    )
                if result.tool_calls:
                    report.last_tool_names = [tc.name for tc in result.tool_calls]
                    turn_outputs: list[tuple[ToolCall, dict, int]] = []
                    awaiting_user = False
                    batches = self._split_batches(result.tool_calls)
                    for batch in batches:
                        names = [tc.name for tc in batch]
                        if (
                            len(batch) > 1
                            and self.settings.agent_parallel_tools
                            and can_parallelize(names)
                        ):
                            batch_outputs: list[tuple[ToolCall, dict, int]] = []
                            async for ev, entry in self._run_parallel_batch(
                                batch,
                                active_doc_path=tool_active_doc_path,
                                conversation_id=conversation_id,
                            ):
                                yield ev
                                if entry is not None:
                                    batch_outputs.append(entry)
                                    turn_outputs.append(entry)
                                    extend_sources(
                                        all_sources, entry[1].get("sources", [])
                                    )
                            if any(tool_awaits_user(out) for _, out, _ in batch_outputs):
                                awaiting_user = True
                                break
                        else:
                            for tc in batch:
                                yield tool_start(
                                    tc.id,
                                    tc.name,
                                    TOOL_LABELS[tc.name],
                                    tc.arguments,
                                )
                                out = None
                                duration_ms = 0
                                async for kind, payload in self._execute_tool_stream(
                                    tc,
                                    active_doc_path=tool_active_doc_path,
                                    conversation_id=conversation_id,
                                ):
                                    if kind == "progress":
                                        yield tool_progress(
                                            tc.id,
                                            tc.name,
                                            payload.get("message", ""),
                                            **{
                                                k: v
                                                for k, v in payload.items()
                                                if k != "message"
                                            },
                                        )
                                    else:
                                        out, duration_ms = payload
                                assert out is not None
                                yield emit_tool_result_sse(tc, out, duration_ms)
                                turn_outputs.append((tc, out, duration_ms))
                                extend_sources(all_sources, out.get("sources", []))
                                if tool_awaits_user(out):
                                    awaiting_user = True
                                    break
                        if awaiting_user:
                            break

                    self._append_tool_turn(messages, result, turn_outputs)
                    tool_call_count += len(turn_outputs)
                    if awaiting_user:
                        report.stop_reason = "awaiting_user"
                        break
                    async for ev in self._drain_injects(
                        messages,
                        turn_id=turn_id,
                        inject_broker=inject_broker,
                        on_inject_applied=on_inject_applied,
                    ):
                        yield ev
                    continue

                report.stop_reason = (
                    "assistant_reply_empty"
                    if not (result.content or "").strip()
                    else "assistant_reply"
                )
                break
            else:
                report.stop_reason = "tool_call_limit"
                yield text_delta(_LIMIT_MSG)

            async for ev in self._defer_remaining_injects(
                turn_id=turn_id, inject_broker=inject_broker
            ):
                yield ev

            duration_ms = int((time.monotonic() - start) * 1000)
            report.done_emitted = True
            yield done(all_sources, duration_ms)
        except asyncio.CancelledError:
            report.stop_reason = "cancelled"
            report.detail = "asyncio.CancelledError during agent loop"
            raise
        except Exception as e:
            report.stop_reason = "error"
            report.detail = str(e)
            raise
        finally:
            report.llm_rounds = llm_rounds
            report.tool_calls_total = tool_call_count
            report.duration_ms = int((time.monotonic() - start) * 1000)
            if report.stop_reason == "unknown":
                if report.done_emitted:
                    report.stop_reason = "done_emitted"
                else:
                    report.stop_reason = "consumer_aborted"
                    report.detail = "SSE consumer closed before done event"
            level = (
                logging.WARNING
                if report.stop_reason
                in (
                    "cancelled",
                    "consumer_aborted",
                    "llm_stream_incomplete",
                    "error",
                    "assistant_reply_empty",
                )
                else logging.INFO
            )
            report.emit(_log, level=level)

    def _split_batches(self, tool_calls: list[ToolCall]) -> list[list[ToolCall]]:
        if not self.settings.agent_parallel_tools:
            return [[tc] for tc in tool_calls]

        batches: list[list[ToolCall]] = []
        parallel_group: list[ToolCall] = []
        max_parallel = self.settings.agent_max_parallel

        def flush_parallel() -> None:
            nonlocal parallel_group
            if not parallel_group:
                return
            for i in range(0, len(parallel_group), max_parallel):
                batches.append(parallel_group[i : i + max_parallel])
            parallel_group = []

        for tc in tool_calls:
            if tc.name in READ_ONLY_TOOLS:
                parallel_group.append(tc)
            else:
                flush_parallel()
                batches.append([tc])
        flush_parallel()
        return batches

    async def _execute_tool(
        self,
        tc: ToolCall,
        *,
        active_doc_path: str | None = None,
        conversation_id: str | None = None,
    ) -> tuple[dict, int]:
        return await self._tool_progress.run(
            tc,
            active_doc_path=active_doc_path,
            conversation_id=conversation_id,
        )

    async def _execute_tool_stream(
        self,
        tc: ToolCall,
        *,
        active_doc_path: str | None = None,
        conversation_id: str | None = None,
    ) -> AsyncIterator[tuple[str, object]]:
        async for item in self._tool_progress.stream(
            tc,
            active_doc_path=active_doc_path,
            conversation_id=conversation_id,
        ):
            yield item

    async def _run_parallel_batch(
        self,
        batch: list[ToolCall],
        *,
        active_doc_path: str | None = None,
        conversation_id: str | None = None,
    ) -> AsyncIterator[tuple[str, tuple[ToolCall, dict, int] | None]]:
        batch_id = uuid.uuid4().hex[:8]
        batch_start = time.monotonic()
        yield parallel_batch_start(batch_id, [tc.name for tc in batch]), None

        for tc in batch:
            yield tool_start(tc.id, tc.name, TOOL_LABELS[tc.name], tc.arguments), None

        async def run_one(tc: ToolCall) -> tuple[ToolCall, dict, int]:
            out, duration_ms = await self._execute_tool(
                tc,
                active_doc_path=active_doc_path,
                conversation_id=conversation_id,
            )
            return tc, out, duration_ms

        tasks = [asyncio.create_task(run_one(tc)) for tc in batch]
        for coro in asyncio.as_completed(tasks):
            tc, out, duration_ms = await coro
            yield emit_tool_result_sse(tc, out, duration_ms), (tc, out, duration_ms)

        batch_duration = int((time.monotonic() - batch_start) * 1000)
        yield parallel_batch_end(batch_id, batch_duration), None

    async def _drain_injects(
        self,
        messages: list[dict],
        *,
        turn_id: str | None,
        inject_broker: TurnInjectBroker | None,
        on_inject_applied,
    ) -> AsyncIterator[str]:
        if not turn_id or inject_broker is None:
            return
        pending = inject_broker.drain(turn_id)
        for item in pending:
            content = self._format_inject_content(item)
            messages.append({"role": "user", "content": content})
            message_id = None
            if on_inject_applied is not None:
                message_id = on_inject_applied(item)
            yield user_inject(
                item.inject_id,
                item.text,
                message_id=message_id,
                client_message_id=item.client_message_id,
                doc_context=item.doc_context,
                primary_doc=item.primary_doc,
                attachments=item.attachments,
            )

    async def _defer_remaining_injects(
        self,
        *,
        turn_id: str | None,
        inject_broker: TurnInjectBroker | None,
    ) -> AsyncIterator[str]:
        if not turn_id or inject_broker is None:
            return
        for item in inject_broker.drain(turn_id):
            yield inject_deferred(item.inject_id)

    @staticmethod
    def _format_inject_content(item: PendingInject) -> str:
        parts: list[str] = []
        docs = item.doc_context or []
        if docs:
            labels = []
            for d in docs:
                if isinstance(d, dict):
                    labels.append(str(d.get("path") or d))
                else:
                    labels.append(str(d))
            parts.append("（补充文档上下文：" + "、".join(labels) + "）")
        if item.attachments:
            parts.append("（附件：" + "、".join(item.attachments) + "）")
        parts.append(item.text)
        return "\n\n".join(parts)

    def _append_tool_turn(
        self,
        messages: list[dict],
        result: ChatWithToolsResult,
        outputs: list[tuple[ToolCall, dict, int]],
    ) -> None:
        # 仅写入已执行的 tool_calls（征询中途停下时可能只跑了部分）
        executed = [tc for tc, _, _ in outputs]
        messages.append(
            {
                "role": "assistant",
                "content": result.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in executed
                ],
            }
        )
        for tc, out, _ in outputs:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": self._serialize_tool_output(out),
                }
            )

    @staticmethod
    def _serialize_tool_output(out: dict) -> str:
        payload = {k: v for k, v in out.items() if k not in _NON_SERIALIZABLE_KEYS}
        return json.dumps(payload, ensure_ascii=False)
