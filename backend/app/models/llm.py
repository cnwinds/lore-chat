from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from openai import OpenAI

from app.config import Settings
from app.engine.background.purpose import current_llm_purpose
from app.logging_config import get_logger
from app.models.candidate import (
    ModelCandidate,
    ModelChain,
    format_vendor_model_label,
    resolve_provider_label,
)
from app.models.cooldown import (
    CooldownStore,
    classify_error,
    is_local_abort,
    shared_cooldown_store,
)
from app.models.effort import format_model_label
from app.models.router import NoCandidateAvailable, Selection, select_candidate
from app.models.thinking import thinking_request_kwargs
from app.models.media import build_user_content_with_media, messages_need_multimodal
from app.models.vision import attachment_signing_secret

_log = get_logger("llm")

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.usage.recorder import UsageRecorder
    from app.engine.usage.request_log import RequestLogRecorder
    from app.engine.background.call_log import BackgroundCallLog


def consolidate_system_messages(messages: list[dict]) -> list[dict]:
    """合并开头的多条 system 消息为一条（部分 OpenAI 兼容 API 只认首条 system）。"""
    from app.engine.agent.prompt_parts import PARTS_KEY, extra_label_from_content

    if not messages:
        return messages
    i = 0
    texts: list[str] = []
    merged_parts: list[dict] = []
    while i < len(messages) and messages[i].get("role") == "system":
        content = messages[i].get("content")
        if isinstance(content, str):
            text = content.strip()
        elif content is not None:
            text = str(content).strip()
        else:
            text = ""
        if text:
            texts.append(text)
        tagged = messages[i].get(PARTS_KEY)
        if tagged:
            merged_parts.extend(list(tagged))
        elif text:
            merged_parts.append(
                {
                    "kind": "extra",
                    "label": extra_label_from_content(text),
                    "text": text,
                }
            )
        i += 1
    if i <= 1:
        return messages
    merged: dict = {"role": "system", "content": "\n\n".join(texts)}
    if merged_parts:
        merged[PARTS_KEY] = merged_parts
    return [merged] + messages[i:]


def _display_model_label(cand: ModelCandidate) -> str:
    """信息流落款：当时显示的「厂家 · 模型[- 档位]」，写入记录后不再按设置回填。"""
    base = format_model_label(
        cand.model,
        thinking=bool(cand.thinking),
        effort=str(cand.effort or ""),
        effort_options=tuple(cand.effort_options or ()),
    )
    vendor = resolve_provider_label(
        getattr(cand, "provider", None),
        getattr(cand, "provider_label", None),
    )
    return format_vendor_model_label(vendor, base)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatWithToolsResult:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class ChatStreamChunk:
    """流式增量：text_delta / think_delta 为逐块文字；final 轮携带完整 result（含 tool_calls）。"""

    text_delta: str | None = None
    think_delta: str | None = None
    result: ChatWithToolsResult | None = None
    model_name: str | None = None
    candidate_id: str | None = None
    failover: bool | None = None
    skipped: list[tuple[str, str]] | None = None


@runtime_checkable
class LLMClient(Protocol):
    def chat(self, messages: list[dict], *, big: bool = False, temperature: float = 0.2) -> str: ...
    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        big: bool = True,
        temperature: float = 0.2,
    ) -> ChatWithToolsResult: ...
    def stream_chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        big: bool = True,
        temperature: float = 0.2,
    ) -> Iterator[ChatStreamChunk]: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def embed_with_model(
        self, texts: list[str]
    ) -> tuple[list[list[float]], str]: ...


def _delta_reasoning(delta: Any) -> str | None:
    """流式思考增量：DeepSeek 等用 reasoning_content；OpenRouter（ox 等）用 reasoning。"""
    for attr in ("reasoning_content", "reasoning"):
        val = getattr(delta, attr, None)
        if isinstance(val, str) and val:
            return val
    return None


def _tool_calls_from_message(message: Any) -> list[ToolCall]:
    out: list[ToolCall] = []
    for tc in message.tool_calls or []:
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        out.append(
            ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=args,
            )
        )
    return out


def _chain_from_big(big: bool) -> ModelChain:
    """兼容旧 API：`big=True` → chat 链，`big=False` → utility 链。"""
    return "chat" if big else "utility"


def _messages_need_video(messages: list[dict], *, kb_path: Path | None = None) -> bool:
    return messages_need_multimodal(messages, kb_path=kb_path, kind="video")


def _messages_need_image(messages: list[dict], *, kb_path: Path | None = None) -> bool:
    return messages_need_multimodal(messages, kb_path=kb_path, kind="image")


class OpenAILLMClient:
    def __init__(
        self,
        settings: Settings,
        usage_recorder: "UsageRecorder | None" = None,
        request_log: "RequestLogRecorder | None" = None,
        background_call_log: "BackgroundCallLog | None" = None,
        cooldown: CooldownStore | None = None,
    ):
        self.settings = settings
        self.usage_recorder = usage_recorder
        self.request_log = request_log
        self.background_call_log = background_call_log
        kb = Path(settings.kb_path)
        from app.models.cooldown import cooldown_path_for_kb

        # 同 kb 路径共用 store，禁止旁路另起内存实例
        self.cooldown = cooldown or shared_cooldown_store(cooldown_path_for_kb(kb))
        self.last_selection: Selection | None = None
        self._client_cache: dict[tuple[str, str], OpenAI] = {}

    def rebind_settings(self, settings: Settings) -> None:
        """热更新 settings，保留同一 CooldownStore。"""
        self.settings = settings
        self._client_cache.clear()

    def _client_for(self, candidate: ModelCandidate) -> OpenAI:
        base = (candidate.base_url or "").rstrip("/")
        key = candidate.api_key or ""
        if not base:
            raise ValueError(
                f"模型候选 {candidate.id or candidate.model!r} 未配置 base_url"
            )
        if not key.strip():
            raise ValueError(
                f"模型候选 {candidate.id or candidate.model!r} 未配置 api_key"
            )
        cache_key = (base, key or "")
        client = self._client_cache.get(cache_key)
        if client is None:
            from app.models.provider_http import provider_extra_headers

            extra = provider_extra_headers(base)
            client = OpenAI(
                api_key=key,
                base_url=base,
                **({"default_headers": extra} if extra else {}),
            )
            self._client_cache[cache_key] = client
        return client

    def _record(self, **kwargs) -> None:
        if self.usage_recorder is None:
            return
        try:
            self.usage_recorder.record(**kwargs)
        except Exception:
            _log.exception("usage record failed")

    def _record_background_call(
        self,
        *,
        cand: ModelCandidate,
        chain: str,
        api_messages: list[dict],
        response: str | None,
        status: str,
        error: str | None,
        duration_ms: int | None,
        temperature: float | None,
        prompt_tokens: int | None,
        completion_tokens: int | None,
    ) -> None:
        blog = self.background_call_log
        pur = current_llm_purpose()
        if blog is None or pur is None:
            return
        try:
            blog.record(
                purpose=pur.purpose,
                variant=pur.variant,
                model=cand.model,
                model_label=_display_model_label(cand),
                candidate_id=cand.id,
                chain=chain if chain in ("utility", "chat", "embed") else None,
                temperature=temperature,
                api_messages=api_messages,
                response=response,
                status=status,
                error=error,
                duration_ms=duration_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                conversation_id=pur.conversation_id,
                scope=pur.scope,
            )
        except Exception:
            _log.exception("background call log failed")

    @staticmethod
    def _cached_tokens_from_usage(usage: Any) -> int | None:
        from app.engine.usage.normalize import cached_tokens_from_usage

        return cached_tokens_from_usage(usage)

    @staticmethod
    def _usage_from_resp(
        resp: Any,
    ) -> tuple[int | None, int | None, int | None, int | None, bool]:
        from app.engine.usage.normalize import usage_from_resp

        return usage_from_resp(resp)

    def _signing_secret(self) -> str:
        return attachment_signing_secret(self.settings)

    def _materialize(
        self, messages: list[dict], candidate: ModelCandidate
    ) -> tuple[list[dict], list[dict]]:
        from app.engine.agent.prompt_parts import PARTS_KEY

        messages = consolidate_system_messages(messages)
        out: list[dict] = []
        annotations: list[dict] = []
        for m in messages:
            msg = dict(m)
            parts = list(msg.pop(PARTS_KEY, None) or [])
            attachments = msg.pop("attachments", None)
            att_list = list(attachments or [])
            if msg.get("role") == "user" and att_list:
                text = msg.get("content")
                if not isinstance(text, str):
                    text = str(text or "")
                msg["content"] = build_user_content_with_media(
                    text,
                    att_list,
                    candidate=candidate,
                    kb_path=Path(self.settings.kb_path),
                    public_base_url=self.settings.public_base_url,
                    signing_secret=self._signing_secret(),
                )
            out.append(msg)
            annotations.append({"parts": parts, "attachments": att_list})
        return out, annotations

    def _request_begin(
        self,
        cand: ModelCandidate,
        api_messages: list[dict],
        annotations: list[dict],
        tools: list[dict] | None,
        kwargs: dict[str, Any],
    ) -> int | None:
        if self.request_log is None:
            return None
        try:
            params = {
                k: v
                for k, v in kwargs.items()
                if k not in ("messages", "tools")
            }
            return self.request_log.begin(
                model=cand.model,
                model_label=_display_model_label(cand),
                candidate_id=cand.id,
                api_messages=api_messages,
                annotations=annotations,
                tools=tools,
                params=params,
            )
        except Exception:
            _log.exception("request_log.begin failed")
            return None

    def _request_finish(self, call_id: int | None, **kwargs) -> None:
        if self.request_log is None or call_id is None:
            return
        try:
            self.request_log.finish(call_id, **kwargs)
        except Exception:
            _log.exception("request_log.finish failed")

    def _select(
        self,
        *,
        big: bool,
        messages: list[dict],
        exclude_ids: set[str] | None = None,
    ) -> Selection:
        chain = _chain_from_big(big)
        require_image = _messages_need_image(
            messages, kb_path=Path(self.settings.kb_path)
        )
        require_video = _messages_need_video(
            messages, kb_path=Path(self.settings.kb_path)
        )
        sel = select_candidate(
            self.settings,
            chain,
            self.cooldown,
            require_image=require_image,
            require_video=require_video,
            exclude_ids=exclude_ids,
        )
        self.last_selection = sel
        return sel

    def _next_after_failure(
        self,
        *,
        failed_id: str,
        exc: BaseException,
        attempted: set[str],
    ) -> None:
        """记录失败并加入本轮排除集；下次 _select 须带 exclude_ids=attempted。"""
        self.cooldown.record_failure(failed_id, classify_error(exc), error=str(exc))
        attempted.add(failed_id)

    def chat(self, messages: list[dict], *, big: bool = False, temperature: float = 0.2) -> str:
        chain = _chain_from_big(big)
        role = chain
        attempted: set[str] = set()
        last_exc: BaseException | None = None
        while True:
            try:
                sel = self._select(big=big, messages=messages, exclude_ids=attempted)
            except NoCandidateAvailable:
                if last_exc:
                    raise last_exc
                raise
            cand = sel.candidate
            client = self._client_for(cand)
            model = cand.model
            api_messages, _annotations = self._materialize(messages, cand)
            t0 = time.monotonic()
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": api_messages,
                "temperature": temperature,
            }
            kwargs.update(thinking_request_kwargs(cand, enable=cand.thinking))
            try:
                resp = client.chat.completions.create(**kwargs)
            except BaseException as e:
                if is_local_abort(e):
                    raise
                last_exc = e
                dur = int((time.monotonic() - t0) * 1000)
                self._record(
                    model=model,
                    kind="chat",
                    role=role,
                    status="error",
                    error=str(e),
                    duration_ms=dur,
                )
                self._record_background_call(
                    cand=cand,
                    chain=chain,
                    api_messages=api_messages,
                    response=None,
                    status="error",
                    error=str(e),
                    duration_ms=dur,
                    temperature=temperature,
                    prompt_tokens=None,
                    completion_tokens=None,
                )
                self._next_after_failure(failed_id=cand.id, exc=e, attempted=attempted)
                continue
            self.cooldown.record_success(cand.id)
            pt, ct, tt, cache, known = self._usage_from_resp(resp)
            dur = int((time.monotonic() - t0) * 1000)
            content = resp.choices[0].message.content or ""
            self._record(
                model=model,
                kind="chat",
                role=role,
                prompt_tokens=pt,
                completion_tokens=ct,
                total_tokens=tt,
                cache_tokens=cache,
                tokens_known=known,
                status="ok",
                duration_ms=dur,
            )
            self._record_background_call(
                cand=cand,
                chain=chain,
                api_messages=api_messages,
                response=content,
                status="ok",
                error=None,
                duration_ms=dur,
                temperature=temperature,
                prompt_tokens=pt,
                completion_tokens=ct,
            )
            return content

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        big: bool = True,
        temperature: float = 0.2,
    ) -> ChatWithToolsResult:
        chain = _chain_from_big(big)
        role = chain
        attempted: set[str] = set()
        last_exc: BaseException | None = None
        while True:
            try:
                sel = self._select(big=big, messages=messages, exclude_ids=attempted)
            except NoCandidateAvailable:
                if last_exc:
                    raise last_exc
                raise
            cand = sel.candidate
            client = self._client_for(cand)
            model = cand.model
            api_messages, annotations = self._materialize(messages, cand)
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": api_messages,
                "temperature": temperature,
            }
            if tools:
                kwargs["tools"] = tools
            kwargs.update(thinking_request_kwargs(cand, enable=cand.thinking))
            t0 = time.monotonic()
            call_id = self._request_begin(
                cand, api_messages, annotations, tools, kwargs
            )
            try:
                resp = client.chat.completions.create(**kwargs)
            except BaseException as e:
                if is_local_abort(e):
                    self._request_finish(
                        call_id,
                        status="aborted",
                        duration_ms=int((time.monotonic() - t0) * 1000),
                        error=str(e),
                    )
                    raise
                last_exc = e
                self._request_finish(
                    call_id,
                    status="error",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                    error=str(e),
                )
                self._record(
                    model=model,
                    kind="chat_tools",
                    role=role,
                    status="error",
                    error=str(e),
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
                self._next_after_failure(failed_id=cand.id, exc=e, attempted=attempted)
                continue
            self.cooldown.record_success(cand.id)
            pt, ct, tt, cache, known = self._usage_from_resp(resp)
            elapsed = int((time.monotonic() - t0) * 1000)
            self._request_finish(
                call_id,
                status="ok",
                prompt_tokens=pt,
                completion_tokens=ct,
                cache_tokens=cache,
                duration_ms=elapsed,
            )
            self._record(
                model=model,
                kind="chat_tools",
                role=role,
                prompt_tokens=pt,
                completion_tokens=ct,
                total_tokens=tt,
                cache_tokens=cache,
                tokens_known=known,
                status="ok",
                duration_ms=elapsed,
            )
            msg = resp.choices[0].message
            return ChatWithToolsResult(
                content=msg.content,
                tool_calls=_tool_calls_from_message(msg),
            )

    def stream_chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        big: bool = True,
        temperature: float = 0.2,
    ) -> Iterator[ChatStreamChunk]:
        chain = _chain_from_big(big)
        role = chain
        attempted: set[str] = set()
        last_exc: BaseException | None = None

        while True:
            try:
                sel = self._select(big=big, messages=messages, exclude_ids=attempted)
            except NoCandidateAvailable:
                if last_exc:
                    raise last_exc
                raise
            cand = sel.candidate
            label = _display_model_label(cand)

            yield ChatStreamChunk(
                model_name=label,
                candidate_id=cand.id,
                failover=sel.failover,
                skipped=list(sel.skipped),
            )

            client = self._client_for(cand)
            model = cand.model
            api_messages, annotations = self._materialize(messages, cand)
            stream_id = uuid.uuid4().hex[:8]
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": api_messages,
                "temperature": temperature,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            if tools:
                kwargs["tools"] = tools
            kwargs.update(thinking_request_kwargs(cand, enable=cand.thinking))
            call_id = self._request_begin(
                cand, api_messages, annotations, tools, kwargs
            )

            _log.info(
                "llm stream start id=%s model=%s chain=%s messages=%d tools=%d failover=%s",
                stream_id,
                model,
                chain,
                len(messages),
                len(tools),
                sel.failover,
            )
            t0 = time.monotonic()
            chunk_count = 0
            content_chars = 0
            think_chars = 0
            tool_delta_count = 0
            finish_reason: str | None = None
            content_parts: list[str] = []
            think_parts: list[str] = []
            tc_acc: dict[int, dict[str, Any]] = {}
            usage_prompt: int | None = None
            usage_completion: int | None = None
            usage_total: int | None = None
            usage_cache: int | None = None
            usage_known = False
            produced_output = False

            try:
                try:
                    stream = client.chat.completions.create(**kwargs)
                except TypeError as e:
                    # 仅当确为 stream_options 不被接受时剥掉重试；其它 TypeError 原样抛出
                    err = str(e)
                    if "stream_options" in kwargs and "stream_options" in err:
                        _log.warning(
                            "llm stream include_usage unsupported id=%s model=%s err=%s; retry without",
                            stream_id,
                            model,
                            e,
                        )
                        kwargs.pop("stream_options", None)
                        stream = client.chat.completions.create(**kwargs)
                    else:
                        raise
                except Exception as e:
                    err = str(e)
                    if "stream_options" in kwargs and (
                        "stream_options" in err or "include_usage" in err
                    ):
                        _log.warning(
                            "llm stream include_usage unsupported id=%s model=%s err=%s; retry without",
                            stream_id,
                            model,
                            e,
                        )
                        kwargs.pop("stream_options", None)
                        stream = client.chat.completions.create(**kwargs)
                    else:
                        raise
                for chunk in stream:
                    chunk_count += 1
                    u = getattr(chunk, "usage", None)
                    if u is not None:
                        usage_prompt = getattr(u, "prompt_tokens", usage_prompt)
                        usage_completion = getattr(
                            u, "completion_tokens", usage_completion
                        )
                        usage_total = getattr(u, "total_tokens", usage_total)
                        cached = self._cached_tokens_from_usage(u)
                        if cached is not None:
                            usage_cache = cached
                        usage_known = (
                            usage_prompt is not None
                            or usage_completion is not None
                            or usage_total is not None
                        )
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
                    delta = choice.delta
                    reasoning = _delta_reasoning(delta)
                    if reasoning:
                        produced_output = True
                        think_parts.append(reasoning)
                        think_chars += len(reasoning)
                        yield ChatStreamChunk(think_delta=reasoning)
                    if delta.content:
                        produced_output = True
                        content_parts.append(delta.content)
                        content_chars += len(delta.content)
                        yield ChatStreamChunk(text_delta=delta.content)
                    for tcd in delta.tool_calls or []:
                        produced_output = True
                        tool_delta_count += 1
                        slot = tc_acc.setdefault(
                            tcd.index, {"id": None, "name": None, "arguments": ""}
                        )
                        if tcd.id:
                            slot["id"] = tcd.id
                        if tcd.function:
                            if tcd.function.name:
                                slot["name"] = tcd.function.name
                            if tcd.function.arguments:
                                slot["arguments"] += tcd.function.arguments
                tool_calls = []
                for idx in sorted(tc_acc):
                    slot = tc_acc[idx]
                    if not slot["name"]:
                        continue
                    try:
                        args = json.loads(slot["arguments"] or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls.append(
                        ToolCall(
                            id=slot["id"] or f"call_{idx}",
                            name=slot["name"],
                            arguments=args,
                        )
                    )
                if tc_acc and not tool_calls:
                    _log.warning(
                        "llm stream id=%s model=%s truncated tool_calls slots=%s",
                        stream_id,
                        model,
                        {
                            k: {
                                "id": v["id"],
                                "name": v["name"],
                                "args_len": len(v["arguments"] or ""),
                            }
                            for k, v in tc_acc.items()
                        },
                    )
            except BaseException as e:
                if is_local_abort(e):
                    self._request_finish(
                        call_id,
                        status="aborted",
                        duration_ms=int((time.monotonic() - t0) * 1000),
                        error=str(e),
                    )
                    raise
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                _log.error(
                    "llm stream error id=%s model=%s ms=%d chunks=%d err=%s",
                    stream_id,
                    model,
                    elapsed_ms,
                    chunk_count,
                    e,
                    exc_info=True,
                )
                self._request_finish(
                    call_id,
                    status="error",
                    duration_ms=elapsed_ms,
                    error=str(e),
                )
                self._record(
                    model=model,
                    kind="stream_tools",
                    role=role,
                    status="error",
                    error=str(e),
                    duration_ms=elapsed_ms,
                )
                last_exc = e
                if produced_output:
                    self.cooldown.record_failure(cand.id, classify_error(e), error=str(e))
                    raise
                self._next_after_failure(failed_id=cand.id, exc=e, attempted=attempted)
                continue

            self.cooldown.record_success(cand.id)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            content = "".join(content_parts) or None
            _log.info(
                "llm stream end id=%s model=%s ms=%d chunks=%d content_chars=%d "
                "think_chars=%d tool_calls=%d finish_reason=%s",
                stream_id,
                model,
                elapsed_ms,
                chunk_count,
                content_chars,
                think_chars,
                len(tool_calls),
                finish_reason,
            )
            self._request_finish(
                call_id,
                status="ok",
                prompt_tokens=usage_prompt,
                completion_tokens=usage_completion,
                cache_tokens=usage_cache,
                duration_ms=elapsed_ms,
            )
            self._record(
                model=model,
                kind="stream_tools",
                role=role,
                prompt_tokens=usage_prompt,
                completion_tokens=usage_completion,
                total_tokens=usage_total,
                cache_tokens=usage_cache,
                tokens_known=usage_known,
                status="ok",
                duration_ms=elapsed_ms,
            )
            yield ChatStreamChunk(
                result=ChatWithToolsResult(content=content, tool_calls=tool_calls),
                model_name=label,
                candidate_id=cand.id,
                failover=sel.failover,
            )
            return

    def embed_with_model(
        self, texts: list[str]
    ) -> tuple[list[list[float]], str]:
        if not texts:
            return [], ""
        attempted: set[str] = set()
        last_exc: BaseException | None = None
        while True:
            try:
                sel = select_candidate(
                    self.settings,
                    "embed",
                    self.cooldown,
                    exclude_ids=attempted,
                )
            except NoCandidateAvailable:
                if last_exc:
                    raise last_exc
                raise
            cand = sel.candidate
            client = self._client_for(cand)
            model = cand.model
            batch_size = 10
            out: list[list[float]] = []
            t0 = time.monotonic()
            prompt_tokens = 0
            total_tokens = 0
            any_known = False
            try:
                for i in range(0, len(texts), batch_size):
                    batch = texts[i : i + batch_size]
                    resp = client.embeddings.create(model=model, input=batch)
                    out.extend(d.embedding for d in resp.data)
                    pt, _, tt, _, known = self._usage_from_resp(resp)
                    if known:
                        any_known = True
                        if pt is not None:
                            prompt_tokens += pt
                        if tt is not None:
                            total_tokens += tt
                        elif pt is not None:
                            total_tokens += pt
            except BaseException as e:
                if is_local_abort(e):
                    raise
                last_exc = e
                self._record(
                    model=model,
                    kind="embed",
                    role="embed",
                    status="error",
                    error=str(e),
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
                self._next_after_failure(
                    failed_id=cand.id, exc=e, attempted=attempted
                )
                continue
            self.cooldown.record_success(cand.id)
            self._record(
                model=model,
                kind="embed",
                role="embed",
                prompt_tokens=prompt_tokens if any_known else None,
                completion_tokens=None,
                total_tokens=total_tokens if any_known else None,
                tokens_known=any_known,
                status="ok",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
            return out, model

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.embed_with_model(texts)[0]


class FakeLLMClient:
    """测试用：脚本化 chat 返回；embed 基于哈希产生确定性向量。"""

    def __init__(
        self,
        chat_responses: list[str] | None = None,
        tool_responses: list[dict] | None = None,
        embed_dim: int = 16,
    ):
        self.chat_responses = list(chat_responses or [])
        self.tool_responses = list(tool_responses or [])
        self.embed_dim = embed_dim
        self.calls: list[dict] = []
        self._i = 0
        self.last_selection = None

    def chat(self, messages: list[dict], *, big: bool = False, temperature: float = 0.2) -> str:
        self.calls.append(
            {
                "messages": messages,
                "big": big,
                "purpose": current_llm_purpose(),
            }
        )
        if self._i < len(self.chat_responses):
            out = self.chat_responses[self._i]
            self._i += 1
            return out
        return ""

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        big: bool = True,
        temperature: float = 0.2,
    ) -> ChatWithToolsResult:
        self.calls.append({"messages": messages, "big": big, "tools": tools})
        if self._i < len(self.tool_responses):
            entry = self.tool_responses[self._i]
            self._i += 1
            return ChatWithToolsResult(
                content=entry.get("content"),
                tool_calls=list(entry.get("tool_calls") or []),
            )
        return ChatWithToolsResult(content="", tool_calls=[])

    def stream_chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        big: bool = True,
        temperature: float = 0.2,
    ) -> Iterator[ChatStreamChunk]:
        think = ""
        if self._i < len(self.tool_responses):
            think = str(self.tool_responses[self._i].get("think") or "")
        result = self.chat_with_tools(messages, tools, big=big, temperature=temperature)
        if think:
            yield ChatStreamChunk(think_delta=think)
        if result.content:
            yield ChatStreamChunk(text_delta=result.content)
        yield ChatStreamChunk(result=result)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs = []
        for t in texts:
            h = hashlib.sha256(t.encode("utf-8")).digest()
            vec = [((h[i % len(h)] / 255.0) * 2 - 1) for i in range(self.embed_dim)]
            vecs.append(vec)
        return vecs

    def embed_with_model(
        self, texts: list[str]
    ) -> tuple[list[list[float]], str]:
        return self.embed(texts), f"fake-embed-{self.embed_dim}"
