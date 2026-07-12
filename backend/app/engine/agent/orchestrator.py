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
from app.engine.agent.prompts import MODE_DEFAULT, build_system_prompt
from app.engine.agent.tools import (
    READ_ONLY_TOOLS,
    TOOL_LABELS,
    ToolRegistry,
    can_parallelize,
    select_tools,
)
from app.models.llm import ChatWithToolsResult, LLMClient, ToolCall

_LIMIT_MSG = "（已达工具调用上限，以上为目前能给出的结论。）"
_NON_SERIALIZABLE_KEYS = frozenset({"hits", "ingest_result"})


def _tool_result_content(tool: str, out: dict) -> str | None:
    if tool == "fetch_url":
        markdown = out.get("markdown")
        return markdown if markdown else None
    return None


def _emit_tool_result(tc: ToolCall, out: dict, duration_ms: int) -> str:
    extra: dict = {}
    if tc.name == "ask_user":
        for key in ("question_id", "question", "options", "multi_select"):
            if key in out:
                extra[key] = out[key]
    elif tc.name in ("search_kb", "web_search"):
        q = tc.arguments.get("query")
        if isinstance(q, str) and q.strip():
            extra["query"] = q.strip()
    elif tc.name == "edit_doc":
        for key in ("preview", "reindex_mode", "applied", "hint", "suggestion"):
            if key in out:
                extra[key] = out[key]
    return tool_result(
        tc.id,
        tc.name,
        out["summary"],
        out.get("sources"),
        duration_ms,
        content=_tool_result_content(tc.name, out),
        **extra,
    )


def _source_key(source: dict) -> str:
    st = source.get("type")
    if st == "kb":
        return f"kb:{source.get('path')}"
    return f"{st}:{source.get('url')}"


def _extend_sources(all_sources: list[dict], new_sources: list[dict]) -> None:
    seen = {_source_key(s) for s in all_sources}
    for s in new_sources:
        key = _source_key(s)
        if key not in seen:
            all_sources.append(s)
            seen.add(key)


class AgentOrchestrator:
    def __init__(self, settings: Settings, llm: LLMClient, tools: ToolRegistry, system_layer=None):
        self.settings = settings
        self.llm = llm
        self.tools = tools
        self.system_layer = system_layer

    async def run(
        self,
        user_text: str,
        *,
        mode: str = MODE_DEFAULT,
        active_doc_path: str | None = None,
        active_doc_paths: list[str] | None = None,
        primary_doc_path: str | None = None,
        history: list[dict] | None = None,
        conversation_id: str | None = None,
        web_enabled: bool = False,
    ) -> AsyncIterator[str]:
        start = time.monotonic()
        system_layer_text = self.system_layer.compose() if self.system_layer else ""
        messages: list[dict] = [
            {
                "role": "system",
                "content": build_system_prompt(mode, system_layer_text, web_enabled),
            },
        ]
        paths = list(active_doc_paths or [])
        primary = primary_doc_path or active_doc_path
        if active_doc_path and active_doc_path not in paths:
            if not paths:
                paths = [active_doc_path]
        if paths:
            lines = []
            for p in paths:
                suffix = "（主文档，默认编辑目标）" if p == primary else "（参考上下文）"
                lines.append(f"- {p}{suffix}")
            messages.append({
                "role": "system",
                "content": "[上下文] 用户当前文档托盘：\n" + "\n".join(lines),
            })
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_text})
        all_sources: list[dict] = []
        tool_call_count = 0
        tools_for_run = select_tools(mode, web_enabled)
        tool_active_doc_path = primary

        while tool_call_count < self.settings.agent_max_tool_calls:
            # 流式消费：文字增量边到边发；最终轮携带完整 result（含 tool_calls）。
            # OpenAI SDK 为同步迭代器，必须放到线程里取 next，否则会堵死事件循环，
            # 导致同进程内 /api/doc 等请求在聊天期间无法响应。
            result: ChatWithToolsResult | None = None
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
                if chunk.text_delta:
                    yield text_delta(chunk.text_delta)
                if chunk.result is not None:
                    result = chunk.result
            if result is None:
                break
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
                        async for ev, entry in self._run_parallel_batch(
                            batch,
                            active_doc_path=tool_active_doc_path,
                            conversation_id=conversation_id,
                        ):
                            yield ev
                            if entry is not None:
                                turn_outputs.append(entry)
                                _extend_sources(all_sources, entry[1].get("sources", []))
                    else:
                        for tc in batch:
                            yield tool_start(tc.id, tc.name, TOOL_LABELS[tc.name], tc.arguments)
                            out, duration_ms = await self._execute_tool(
                                tc,
                                active_doc_path=tool_active_doc_path,
                                conversation_id=conversation_id,
                            )
                            yield _emit_tool_result(tc, out, duration_ms)
                            turn_outputs.append((tc, out, duration_ms))
                            _extend_sources(all_sources, out.get("sources", []))

                self._append_tool_turn(messages, result, turn_outputs)
                tool_call_count += len(result.tool_calls)
                continue

            # 无工具调用：最终答复文字已在上面的流式循环中逐块发出
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

    async def _execute_tool(
        self,
        tc: ToolCall,
        *,
        active_doc_path: str | None = None,
        conversation_id: str | None = None,
    ) -> tuple[dict, int]:
        t0 = time.monotonic()
        try:
            out = await self.tools.execute(
                tc.name,
                tc.arguments,
                active_doc_path=active_doc_path,
                conversation_id=conversation_id,
            )
        except Exception as e:
            out = {
                "summary": f"工具执行失败：{e}",
                "sources": [],
                "error": str(e),
            }
        duration_ms = int((time.monotonic() - t0) * 1000)
        return out, duration_ms

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
            yield _emit_tool_result(tc, out, duration_ms), (tc, out, duration_ms)

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
