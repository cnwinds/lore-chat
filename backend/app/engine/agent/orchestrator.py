from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator

from app.config import Settings
from app.engine.agent.events import (
    done,
    parallel_batch_end,
    parallel_batch_start,
    text_delta,
    tool_result,
    tool_start,
)
from app.engine.agent.prompts import build_system_prompt
from app.engine.agent.tools import (
    READ_ONLY_TOOLS,
    TOOL_DEFINITIONS,
    TOOL_LABELS,
    ToolRegistry,
    can_parallelize,
)
from app.models.llm import ChatWithToolsResult, LLMClient, ToolCall

_LIMIT_MSG = "（已达工具调用上限，以上为目前能给出的结论。）"
_NON_SERIALIZABLE_KEYS = frozenset({"hits", "ingest_result"})


class AgentOrchestrator:
    def __init__(self, settings: Settings, llm: LLMClient, tools: ToolRegistry):
        self.settings = settings
        self.llm = llm
        self.tools = tools

    async def run(self, user_text: str, *, mode: str = "default") -> AsyncIterator[str]:
        start = time.monotonic()
        messages: list[dict] = [
            {"role": "system", "content": build_system_prompt(mode)},
            {"role": "user", "content": user_text},
        ]
        all_sources: list[dict] = []
        tool_call_count = 0

        while tool_call_count < self.settings.agent_max_tool_calls:
            result = self.llm.chat_with_tools(messages, TOOL_DEFINITIONS, big=True)
            if result.tool_calls:
                turn_outputs: list[tuple[ToolCall, dict, int]] = []
                batches = self._split_batches(result.tool_calls)
                for batch in batches:
                    names = [tc.name for tc in batch]
                    if (
                        len(batch) > 1
                        and self.settings.agent_parallel_tools
                        and can_parallelize(names)
                    ):
                        async for ev, entry in self._run_parallel_batch(batch):
                            yield ev
                            if entry is not None:
                                turn_outputs.append(entry)
                                all_sources.extend(entry[1].get("sources", []))
                    else:
                        for tc in batch:
                            yield tool_start(tc.id, tc.name, TOOL_LABELS[tc.name], tc.arguments)
                            out, duration_ms = await self._execute_tool(tc)
                            yield tool_result(
                                tc.id,
                                tc.name,
                                out["summary"],
                                out.get("sources"),
                                duration_ms,
                            )
                            turn_outputs.append((tc, out, duration_ms))
                            all_sources.extend(out.get("sources", []))

                self._append_tool_turn(messages, result, turn_outputs)
                tool_call_count += len(result.tool_calls)
                continue

            if result.content:
                yield text_delta(result.content)
            break
        else:
            yield text_delta(_LIMIT_MSG)

        yield done(all_sources, int((time.monotonic() - start) * 1000))

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

    async def _execute_tool(self, tc: ToolCall) -> tuple[dict, int]:
        t0 = time.monotonic()
        out = await self.tools.execute(tc.name, tc.arguments)
        duration_ms = int((time.monotonic() - t0) * 1000)
        return out, duration_ms

    async def _run_parallel_batch(
        self, batch: list[ToolCall]
    ) -> AsyncIterator[tuple[str, tuple[ToolCall, dict, int] | None]]:
        batch_id = uuid.uuid4().hex[:8]
        batch_start = time.monotonic()
        yield parallel_batch_start(batch_id, [tc.name for tc in batch]), None

        for tc in batch:
            yield tool_start(tc.id, tc.name, TOOL_LABELS[tc.name], tc.arguments), None

        async def run_one(tc: ToolCall) -> tuple[ToolCall, dict, int]:
            out, duration_ms = await self._execute_tool(tc)
            return tc, out, duration_ms

        tasks = [asyncio.create_task(run_one(tc)) for tc in batch]
        for coro in asyncio.as_completed(tasks):
            tc, out, duration_ms = await coro
            yield tool_result(
                tc.id,
                tc.name,
                out["summary"],
                out.get("sources"),
                duration_ms,
            ), (tc, out, duration_ms)

        batch_duration = int((time.monotonic() - batch_start) * 1000)
        yield parallel_batch_end(batch_id, batch_duration), None

    def _append_tool_turn(
        self,
        messages: list[dict],
        result: ChatWithToolsResult,
        outputs: list[tuple[ToolCall, dict, int]],
    ) -> None:
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
                    for tc in result.tool_calls
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

    def _serialize_tool_output(self, out: dict) -> str:
        payload = {k: v for k, v in out.items() if k not in _NON_SERIALIZABLE_KEYS}
        return json.dumps(payload, ensure_ascii=False)
