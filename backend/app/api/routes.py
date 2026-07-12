from __future__ import annotations

import io
import json

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.engine.agent.events import error_event, now_ts
from app.logging_config import get_logger

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
    active_doc_path: str | None = None


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
                self.all_sources.extend(block["sources"])

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
            seen = {json.dumps(s, sort_keys=True) for s in self.all_sources}
            for source in data.get("sources") or []:
                key = json.dumps(source, sort_keys=True)
                if key not in seen:
                    self.all_sources.append(source)
                    seen.add(key)
            if data.get("total_duration_ms") is not None:
                self.total_duration_ms = data["total_duration_ms"]


def _accumulate_timeline(
    acc: _TimelineAccumulator, ev: str
) -> None:
    parsed = _parse_sse(ev)
    if parsed:
        acc.accumulate(parsed[0], parsed[1])


def _ingest_from_write_kb_result(data: dict) -> dict:
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
    result: dict | None = None
    async for ev in agent.run(text, mode="force_write"):
        parsed = _parse_sse(ev)
        if not parsed:
            continue
        event_type, data = parsed
        if event_type == "tool_result" and data.get("tool") == "write_kb":
            result = _ingest_from_write_kb_result(data)
    if result is None:
        raise HTTPException(502, "录入失败: Agent 未调用 write_kb")
    return result


def _reindex_conversation(c, cid: str, conv: dict) -> None:
    """未归档会话进全文索引，作为归档前的可检索兜底；已归档则移出索引。"""
    try:
        if conv.get("summarized"):
            c.indexer.remove_conversation(cid)
            return
        text = c.conversations.conversation_text(conv)
        c.indexer.index_conversation(cid, text)
        c.conversations.clear_dirty(cid)
    except Exception:
        get_logger("routes").warning("会话重索引失败 cid=%s", cid, exc_info=True)


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
    text_parts: list[str] = []
    sources: list[dict] = []
    async for ev in agent.run(query, mode="no_write"):
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
    c = _c(request)
    try:
        return await _consume_agent_ingest(c.agent, body.text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"录入失败: {e}") from e


@router.post("/ask")
async def ask(body: AskBody, request: Request):
    try:
        return await _consume_agent_ask(_c(request).agent, body.query)
    except Exception as e:
        raise HTTPException(502, f"问答失败: {e}") from e


@router.post("/chat")
async def chat(body: ChatBody, request: Request):
    c = _c(request)
    if body.conversation_id:
        try:
            c.conversations.get(body.conversation_id)
        except KeyError as e:
            raise HTTPException(404, "对话不存在") from e

    async def event_generator():
        acc = _TimelineAccumulator()
        assistant_ts = now_ts()
        history: list[dict] = []
        if body.conversation_id:
            history = c.conversations.llm_history(c.conversations.get(body.conversation_id))
        try:
            async for ev in c.agent.run(
                body.text,
                mode="default",
                active_doc_path=body.active_doc_path,
                history=history,
                conversation_id=body.conversation_id,
            ):
                yield ev
                _accumulate_timeline(acc, ev)
            assistant_msg: dict = {
                "role": "assistant",
                "ts": assistant_ts,
                "timeline": acc.timeline,
                "sources": acc.all_sources,
            }
            if acc.total_duration_ms is not None:
                assistant_msg["total_duration_ms"] = acc.total_duration_ms
            if body.conversation_id:
                conv = c.conversations.append_exchange(
                    body.conversation_id,
                    body.text,
                    assistant_msg,
                    user_ts=now_ts(),
                )
                _reindex_conversation(c, body.conversation_id, conv)
        except Exception as e:
            yield error_event(str(e))

    return StreamingResponse(event_generator(), media_type="text/event-stream")


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
    abs_path = c.repo._abs(rel)
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
    c.repo.write_doc(body.path, doc.meta, body.body, commit_msg=f"edit: {body.path}")
    c.indexer.reindex_doc(body.path, body.body)
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
        c.conversations.mark_summarized(cid, result.rel_path)
        c.indexer.remove_conversation(cid)
    return result.__dict__


@router.delete("/conversations/{cid}")
async def delete_conversation(cid: str, request: Request):
    try:
        _c(request).conversations.delete(cid)
    except KeyError as e:
        raise HTTPException(404, "对话不存在") from e
    return {"ok": True}
