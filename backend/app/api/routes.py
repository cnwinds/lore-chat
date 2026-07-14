from __future__ import annotations

import asyncio
import io
import json
import uuid

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.engine.agent.events import done, error_event, text_delta
from app.engine.source_key import extend_sources
from app.engine.agent.prompts import MODE_DEFAULT, MODE_FORCE_WRITE, MODE_NO_WRITE
from app.engine.conversations import TurnInProgress
from app.engine.patch import diff_affected_range

router = APIRouter(prefix="/api")


class IngestBody(BaseModel):
    text: str


class AskBody(BaseModel):
    query: str


class ResolveBody(BaseModel):
    choice: str | None = None
    choices: list[str] | None = None
    conversation_id: str | None = None


class ChatBody(BaseModel):
    text: str
    conversation_id: str | None = None
    client_message_id: str | None = None
    active_doc_path: str | None = None  # backward compat
    active_doc_paths: list[str] = []
    primary_doc_path: str | None = None
    web_enabled: bool = False
    attachments: list[str] = []


def _normalize_chat_docs(body: ChatBody) -> tuple[list[str], str | None]:
    paths = list(body.active_doc_paths)
    primary = body.primary_doc_path
    if body.active_doc_path:
        if not paths:
            paths = [body.active_doc_path]
        if primary is None:
            primary = body.active_doc_path
    if primary is not None and primary not in paths:
        raise HTTPException(400, "primary_doc_path 必须在 active_doc_paths 内")
    return paths, primary


class AppendMessagesBody(BaseModel):
    messages: list[dict]


class UpdateDocBody(BaseModel):
    path: str
    body: str


class MergeBody(BaseModel):
    paths: list[str]
    instruction: str = ""
    order: list[str] | None = None
    title: str | None = None


class ResolveMergeSourcesBody(BaseModel):
    delete_paths: list[str]


def _c(request: Request):
    return request.app.state.container


def _parse_sse(ev: str) -> tuple[str, dict] | None:
    lines = ev.strip().split("\n")
    event_type = None
    data = None
    for line in lines:
        if line.startswith("event: "):
            event_type = line[7:]
        elif line.startswith("data: "):
            data = json.loads(line[6:])
    if event_type and data is not None:
        return event_type, data
    return None


class _TimelineAccumulator:
    def __init__(self) -> None:
        self.timeline: list[dict] = []
        self.all_sources: list[dict] = []
        self.total_duration_ms: int | None = None
        self.assistant_text: str = ""
        self._tools: dict[str, dict] = {}
        self._parallel: dict[str, dict] = {}
        self._active_parallel: str | None = None
        self._text_block: dict | None = None

    def accumulate(self, event_type: str, data: dict) -> None:
        if event_type == "tool_start":
            block = {
                "type": "tool",
                "id": data["id"],
                "tool": data["tool"],
                "label": data["label"],
                "ts": data["ts"],
                "status": "running",
            }
            inp = data.get("input")
            if isinstance(inp, dict) and inp.get("query"):
                block["query"] = inp["query"]
            self._tools[data["id"]] = block
            if self._active_parallel:
                self._parallel[self._active_parallel]["children"].append(block)
            else:
                self.timeline.append(block)
            self._text_block = None

        elif event_type == "tool_result":
            block = self._tools.get(data["id"])
            if block:
                block["status"] = "done"
                block["summary"] = data.get("summary", "")
                block["sources"] = data.get("sources") or []
                if data.get("content"):
                    block["content"] = data["content"]
                if data.get("duration_ms") is not None:
                    block["duration_ms"] = data["duration_ms"]
                if data.get("query"):
                    block["query"] = data["query"]
                for key in ("question_id", "question", "options", "multi_select"):
                    if data.get(key) is not None:
                        block[key] = data[key]
                for key in ("preview", "reindex_mode", "applied"):
                    if data.get(key) is not None:
                        block[key] = data[key]
                extend_sources(self.all_sources, block.get("sources") or [])

        elif event_type == "parallel_batch_start":
            block = {
                "type": "parallel",
                "batch_id": data["batch_id"],
                "ts": data["ts"],
                "children": [],
            }
            self._parallel[data["batch_id"]] = block
            self.timeline.append(block)
            self._active_parallel = data["batch_id"]
            self._text_block = None

        elif event_type == "parallel_batch_end":
            block = self._parallel.get(data["batch_id"])
            if block and data.get("duration_ms") is not None:
                block["duration_ms"] = data["duration_ms"]
            if self._active_parallel == data["batch_id"]:
                self._active_parallel = None

        elif event_type == "text_delta":
            delta = data.get("delta", "")
            self.assistant_text += delta
            if self._text_block is None:
                self._text_block = {
                    "type": "text",
                    "ts": data["ts"],
                    "content": delta,
                }
                self.timeline.append(self._text_block)
            else:
                self._text_block["content"] += delta

        elif event_type == "done":
            extend_sources(self.all_sources, data.get("sources") or [])
            if data.get("total_duration_ms") is not None:
                self.total_duration_ms = data["total_duration_ms"]


# ---------------------------------------------------------------------------
# 同步机器 API：/ingest、/ask
#
# 产品 UI 使用 POST /api/chat（SSE）；本区端点保留给测试、脚本与集成调用：
#   - 结果更确定（force_write / no_write 硬模式）
#   - 同步 JSON，无需解析 SSE
# 详见 docs/superpowers/specs/2026-07-12-ingest-ask-api-design.md
# ---------------------------------------------------------------------------


def _ingest_from_write_kb_result(data: dict) -> dict:
    """将 write_kb 的 tool_result 转为 IngestResult 兼容的 JSON。"""
    status = data.get("status")
    rel_path = data.get("rel_path")
    if not rel_path:
        sources = data.get("sources") or []
        rel_path = sources[0]["path"] if sources and sources[0].get("path") else None
    if status is None:
        # 兜底：老格式无结构化状态时按 rel_path 推断
        status = "saved" if rel_path else "rejected"
    return {
        "status": status,
        "rel_path": rel_path,
        "question_id": data.get("question_id"),
        "message": data.get("summary", ""),
    }


async def _consume_agent_ingest(agent, text: str) -> dict:
    """消费 Agent 一轮 force_write，返回首个 write_kb 的结构化结果。

    未调用 write_kb 时由路由层抛 502。不传 conversation_id / web_enabled。
    """
    result: dict | None = None
    async for ev in agent.run(text, mode=MODE_FORCE_WRITE):
        parsed = _parse_sse(ev)
        if not parsed:
            continue
        event_type, data = parsed
        if event_type == "tool_result" and data.get("tool") == "write_kb":
            result = _ingest_from_write_kb_result(data)
    if result is None:
        raise HTTPException(502, "录入失败: Agent 未调用 write_kb")
    return result


def _merge_session_view(c, session: dict) -> dict:
    user_modified = False
    rel_path = session.get("new_path")
    if rel_path:
        try:
            body = c.repo.read_doc(rel_path).body
            user_modified = c.merge_sessions.user_modified(session["id"], body)
        except (FileNotFoundError, KeyError):
            user_modified = False
    return {"session": session, "user_modified": user_modified}


async def _consume_agent_ask(agent, query: str) -> dict:
    """消费 Agent 一轮 no_write，拼接正文并返回 sources。

    write_kb 已被 select_tools 硬门移除。不传 conversation_id / web_enabled。
    """
    text_parts: list[str] = []
    sources: list[dict] = []
    async for ev in agent.run(query, mode=MODE_NO_WRITE):
        parsed = _parse_sse(ev)
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
        if s.get("type") == "kb" and "/attachments/" in (s.get("path") or "")
    ]
    return {"text": "".join(text_parts), "sources": sources, "attachments": attachments}


@router.post("/ingest")
async def ingest(body: IngestBody, request: Request):
    """强制落库（测试/脚本 API）。产品聊天请用 POST /api/chat。"""
    c = _c(request)
    try:
        return await _consume_agent_ingest(c.agent, body.text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"录入失败: {e}") from e


@router.post("/ask")
async def ask(body: AskBody, request: Request):
    """只读问答（测试/脚本 API）。产品聊天请用 POST /api/chat。"""
    try:
        return await _consume_agent_ask(_c(request).agent, body.query)
    except Exception as e:
        raise HTTPException(502, f"问答失败: {e}") from e


async def _chat_stream_no_persist(c, body: ChatBody, paths: list[str], primary: str | None):
    """无 conversation_id：不持久化，纯流式转发（沿用旧行为）。"""
    try:
        async for ev in c.agent.run(
            body.text,
            mode=MODE_DEFAULT,
            active_doc_path=primary,
            active_doc_paths=paths,
            primary_doc_path=primary,
            history=None,
            conversation_id=None,
            web_enabled=body.web_enabled,
        ):
            yield ev
    except Exception as e:
        yield error_event(str(e))


async def _chat_replay(turn: dict):
    """turn 已 complete/interrupted：从已存 timeline 重放，不再次运行 Agent。"""
    assistant = turn.get("assistant_message") or {}
    for block in assistant.get("timeline") or []:
        if block.get("type") == "text" and block.get("content"):
            yield text_delta(block["content"])
    yield done(assistant.get("sources") or [], assistant.get("total_duration_ms") or 0)


async def _chat_stream_and_persist(
    c,
    body: ChatBody,
    cid: str,
    turn: dict,
    history: list[dict],
    paths: list[str],
    primary: str | None,
):
    acc = _TimelineAccumulator()
    assistant_saved = False

    def _finalize(status: str, error: str | None = None) -> None:
        nonlocal assistant_saved
        if assistant_saved:
            return
        assistant: dict = {
            "text": acc.assistant_text,
            "timeline": acc.timeline,
            "sources": acc.all_sources,
            "total_duration_ms": acc.total_duration_ms,
            "status": status,
        }
        if error is not None:
            assistant["error"] = error
        c.conversations.finalize_turn(cid, turn_id=turn["turn_id"], assistant=assistant)
        assistant_saved = True

    try:
        async for ev in c.agent.run(
            body.text,
            mode=MODE_DEFAULT,
            active_doc_path=primary,
            active_doc_paths=paths,
            primary_doc_path=primary,
            history=history,
            conversation_id=cid,
            web_enabled=body.web_enabled,
        ):
            parsed = _parse_sse(ev)
            if parsed:
                acc.accumulate(*parsed)
                if parsed[0] == "done":
                    # 拦截最终 done：先落库再把事件转发给客户端。
                    _finalize("complete")
            yield ev
    except asyncio.CancelledError:
        def _finalize_partial() -> None:
            if acc.timeline or acc.assistant_text:
                _finalize("interrupted")

        await asyncio.shield(asyncio.to_thread(_finalize_partial))
        raise
    except Exception as e:
        _finalize("interrupted", error=str(e))
        yield error_event(str(e))
    finally:
        if not assistant_saved and (acc.timeline or acc.assistant_text):
            _finalize("interrupted")


@router.post("/chat")
async def chat(body: ChatBody, request: Request):
    """产品主入口：SSE 流式 Agent，会话持久化与时间线。

    有 conversation_id 时，在返回 StreamingResponse 之前完成 begin_turn：
    - TurnInProgress → 409（不会已经发出 200 响应头）
    - turn 已 complete/interrupted（重复 client_message_id 重试）→ 重放，不再跑 Agent
    - 否则流式运行 Agent，并在收到 done 前 finalize_turn 落库
    """
    c = _c(request)
    paths, primary = _normalize_chat_docs(body)
    if body.conversation_id:
        try:
            c.conversations.get(body.conversation_id)
        except KeyError as e:
            raise HTTPException(404, "对话不存在") from e

    if not body.conversation_id:
        return StreamingResponse(
            _chat_stream_no_persist(c, body, paths, primary),
            media_type="text/event-stream",
        )

    cid = body.conversation_id
    # 必须在 begin_turn 之前快照历史：begin_turn 会写入本轮用户消息，
    # 传给 Agent 的 history 不应包含这条尚未回复的新消息。
    history = c.conversations.llm_history(c.conversations.get(cid))
    client_message_id = body.client_message_id or uuid.uuid4().hex
    try:
        turn = c.conversations.begin_turn(
            cid,
            user_text=body.text,
            client_message_id=client_message_id,
            observation_allowed=False,
            doc_context=paths or None,
            primary_doc=primary,
            attachments=body.attachments or None,
        )
    except TurnInProgress as e:
        raise HTTPException(
            409,
            detail={"code": "turn_in_progress", "retry_after_ms": e.retry_after_ms},
        )

    if turn.get("status", "running") != "running":
        return StreamingResponse(_chat_replay(turn), media_type="text/event-stream")

    return StreamingResponse(
        _chat_stream_and_persist(c, body, cid, turn, history, paths, primary),
        media_type="text/event-stream",
    )


@router.post("/upload")
async def upload(
    request: Request,
    file: UploadFile = File(...),
    category: str = Form("未分类"),
):
    c = _c(request)
    data = await file.read()
    rel = c.repo.save_attachment(
        category,
        file.filename,
        data,
        commit_msg=f"add attachment {file.filename}",
    )
    abs_path = c.repo.abs_path(rel)
    from app.index.extract import extract_text

    text = extract_text(abs_path)
    if text.strip():
        c.indexer.reindex_doc(rel, text)
    c.repo.log_change(
        f"上传附件 {rel}",
        commit_msg=f"chore: changelog upload {file.filename}",
    )
    return {"attachment": rel, "indexed": bool(text.strip())}


@router.get("/download")
async def download(path: str, request: Request):
    try:
        data = _c(request).repo.get_attachment(path)
    except FileNotFoundError:
        raise HTTPException(404, "文件不存在")
    filename = path.rsplit("/", 1)[-1]
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/tree")
async def tree(request: Request):
    return {"docs": _c(request).repo.list_tree()}


@router.get("/doc")
async def doc(path: str, request: Request):
    try:
        d = _c(request).repo.read_doc(path)
    except FileNotFoundError:
        raise HTTPException(404, "文档不存在")
    return {"rel_path": d.rel_path, "meta": d.meta, "body": d.body}


@router.put("/doc")
async def update_doc(body: UpdateDocBody, request: Request):
    c = _c(request)
    if not c.repo.is_writable(body.path):
        raise HTTPException(403, "禁止编辑该路径")
    try:
        doc = c.repo.read_doc(body.path)
    except FileNotFoundError:
        raise HTTPException(404, "文档不存在")
    old_body = doc.body
    c.repo.write_doc(body.path, doc.meta, body.body, commit_msg=f"edit: {body.path}")
    if old_body != body.body:
        affected_start, affected_end = diff_affected_range(old_body, body.body)
        c.indexer.reindex_doc_after_edit(
            body.path,
            old_body,
            body.body,
            affected_start,
            affected_end,
        )
    c.repo.log_change(f"用户编辑 {body.path}")
    d = c.repo.read_doc(body.path)
    return {"rel_path": d.rel_path, "meta": d.meta, "body": d.body}


@router.post("/docs/merge")
async def merge_docs(body: MergeBody, request: Request):
    c = _c(request)
    result = c.organizer.merge_documents(
        body.paths,
        instruction=body.instruction,
        order=body.order,
        title_hint=body.title,
        merge_sessions=c.merge_sessions,
    )
    return result.__dict__


@router.get("/docs/merge/active")
async def get_active_merge(path: str, request: Request):
    c = _c(request)
    session = c.merge_sessions.find_active_by_path(path)
    if not session:
        raise HTTPException(404, "未找到进行中的合并会话")
    return _merge_session_view(c, session)


@router.get("/docs/merge/{merge_id}")
async def get_merge(merge_id: str, request: Request):
    c = _c(request)
    try:
        session = c.merge_sessions.get(merge_id)
    except KeyError as e:
        raise HTTPException(404, "合并会话不存在") from e
    return _merge_session_view(c, session)


@router.post("/docs/merge/{merge_id}/regenerate")
async def regenerate_merge(merge_id: str, request: Request):
    c = _c(request)
    try:
        result = c.organizer.regenerate_merge(merge_id, merge_sessions=c.merge_sessions)
    except KeyError as e:
        raise HTTPException(404, "合并会话不存在") from e
    return result.__dict__


@router.post("/docs/merge/{merge_id}/accept")
async def accept_merge(merge_id: str, request: Request):
    c = _c(request)
    try:
        result = c.organizer.accept_merge(merge_id, merge_sessions=c.merge_sessions)
    except KeyError as e:
        raise HTTPException(404, "合并会话不存在") from e
    return result.__dict__


@router.post("/docs/merge/{merge_id}/reject")
async def reject_merge(merge_id: str, request: Request):
    c = _c(request)
    try:
        result = c.organizer.reject_merge(merge_id, merge_sessions=c.merge_sessions)
    except KeyError as e:
        raise HTTPException(404, "合并会话不存在") from e
    return result.__dict__


@router.post("/docs/merge/{merge_id}/resolve-sources")
async def resolve_merge_sources(
    merge_id: str, body: ResolveMergeSourcesBody, request: Request
):
    c = _c(request)
    try:
        result = c.organizer.resolve_merge_sources(
            merge_id,
            body.delete_paths,
            merge_sessions=c.merge_sessions,
        )
    except KeyError as e:
        raise HTTPException(404, "合并会话不存在") from e
    return result.__dict__


@router.get("/questions")
async def questions(request: Request):
    return {"questions": _c(request).pending.list_open()}


def _is_agent_question(q: dict) -> bool:
    payload = q.get("payload", {})
    kind = payload.get("kind")
    if kind == "agent":
        return True
    if kind == "merge_sources":
        return False
    # organizer 歧义确认问题带 decision/content，走 resolve_pending
    return not payload.get("decision") and not payload.get("content")


@router.post("/questions/{qid}/resolve")
async def resolve(qid: str, body: ResolveBody, request: Request):
    c = _c(request)
    try:
        q = c.pending.get(qid)
    except KeyError as e:
        raise HTTPException(404, "问题不存在") from e
    conversation_context = ""
    if body.conversation_id:
        try:
            conv = c.conversations.get(body.conversation_id)
            conversation_context = c.conversations.context_excerpt(conv)
        except KeyError as e:
            raise HTTPException(404, "对话不存在") from e
    chosen_ids = body.choices or ([body.choice] if body.choice else [])
    chosen_labels = [
        o["label"] for o in q.get("options", []) if o.get("id") in chosen_ids
    ]
    payload = q.get("payload", {})
    if payload.get("kind") == "merge_sources":
        if not body.choices:
            raise HTTPException(400, "该问题请使用 choices 提交要删除的源文档")
        merge_id = payload.get("merge_id")
        if not merge_id:
            raise HTTPException(400, "该问题缺少 merge_id")
        c.pending.resolve_many(qid, body.choices)
        result = c.organizer.resolve_merge_sources(
            merge_id,
            list(body.choices),
            merge_sessions=c.merge_sessions,
        )
    elif body.choices:
        if _is_agent_question(q):
            result = c.organizer.resolve_agent_choices(
                qid, body.choices, conversation_context=conversation_context
            )
        else:
            raise HTTPException(400, "该问题不支持多选")
    elif body.choice:
        if _is_agent_question(q):
            result = c.organizer.resolve_agent_choices(
                qid, [body.choice], conversation_context=conversation_context
            )
        else:
            result = c.organizer.resolve_pending(qid, body.choice)
    else:
        raise HTTPException(400, "请提供 choice 或 choices")

    if body.conversation_id and chosen_labels:
        try:
            c.conversations.mark_question_resolved(
                body.conversation_id, qid, "、".join(chosen_labels)
            )
        except Exception:
            pass
    return result.__dict__


@router.get("/conversations")
async def list_conversations(request: Request):
    return {"conversations": _c(request).conversations.list_all()}


@router.post("/conversations")
async def create_conversation(request: Request):
    cid = _c(request).conversations.create()
    return {"id": cid}


@router.get("/conversations/{cid}")
async def get_conversation(cid: str, request: Request):
    try:
        return _c(request).conversations.get(cid)
    except KeyError as e:
        raise HTTPException(404, "对话不存在") from e


@router.post("/conversations/{cid}/messages")
async def append_conversation_messages(
    cid: str, body: AppendMessagesBody, request: Request
):
    try:
        return _c(request).conversations.append_messages(cid, body.messages)
    except KeyError as e:
        raise HTTPException(404, "对话不存在") from e


@router.post("/conversations/{cid}/summarize")
async def summarize_conversation(cid: str, request: Request):
    c = _c(request)
    try:
        conv = c.conversations.get(cid)
    except KeyError as e:
        raise HTTPException(404, "对话不存在") from e
    from app.engine.conversations import ConversationStore

    transcript = ConversationStore.full_transcript(conv)
    system_rules = c.system_layer.compose() if c.system_layer else ""
    try:
        # 同步执行：内含 Chroma/SQLite 检索，不能放进 run_in_threadpool（会触发跨线程 DB 错误）
        result = c.organizer.summarize_conversation(
            transcript,
            system_rules=system_rules,
            conversation_id=cid,
        )
    except Exception as e:
        raise HTTPException(502, f"归档失败: {e}") from e
    if result.status == "saved" and result.rel_path:
        # 归档后仍保留原始消息的全文索引，不清空会话消息级 FTS。
        c.conversations.mark_summarized(cid, result.rel_path)
    return result.__dict__


@router.delete("/conversations/{cid}")
async def delete_conversation(cid: str, request: Request):
    c = _c(request)
    try:
        c.conversations.delete(
            cid, conversation_fts=c.conversation_fts, indexer=c.indexer
        )
    except KeyError as e:
        raise HTTPException(404, "对话不存在") from e
    return {"ok": True}
