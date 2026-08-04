from __future__ import annotations

import io
import json
import uuid

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.engine.knowledge_writer import KnowledgeWriter
from app.engine.chat.session_runner import consume_agent_ask, consume_agent_ingest
from app.engine.conversations import TurnInProgress
from app.engine.patch import diff_affected_range

router = APIRouter(prefix="/api")


def _kb_path_exists_detail(
    rel_path: str, message: str, suggested_filename: str
) -> dict:
    return {
        "code": "PATH_EXISTS",
        "path": rel_path,
        "message": message,
        "suggested_filename": suggested_filename,
    }


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
    observation_allowed: bool = True


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


def _kb_tree_service(request: Request):
    from app.engine.kb_tree_service import KbTreeService

    c = _c(request)
    return c, KbTreeService(c.repo, c.knowledge_writer, c.index_revision)


class SummarizeBody(BaseModel):
    directory: str
    filename: str


class KbMoveBody(BaseModel):
    from_path: str
    to_directory: str
    to_filename: str | None = None


class KbDeleteBody(BaseModel):
    path: str


# ---------------------------------------------------------------------------
# 同步机器 API：/ingest、/ask
#
# 产品 UI 使用 POST /api/chat（SSE）；本区端点保留给测试、脚本与集成调用：
#   - 结果更确定（force_write / no_write 硬模式）
#   - 同步 JSON，无需解析 SSE
# 详见 docs/superpowers/specs/2026-07-12-ingest-ask-api-design.md
# ---------------------------------------------------------------------------


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


@router.post("/ingest")
async def ingest(body: IngestBody, request: Request):
    """强制落库（测试/脚本 API）。产品聊天请用 POST /api/chat。"""
    c = _c(request)
    try:
        return await consume_agent_ingest(c.agent, body.text)
    except RuntimeError as e:
        raise HTTPException(502, f"录入失败: {e}") from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"录入失败: {e}") from e


@router.post("/ask")
async def ask(body: AskBody, request: Request):
    """只读问答（测试/脚本 API）。产品聊天请用 POST /api/chat。"""
    try:
        return await consume_agent_ask(_c(request).agent, body.query)
    except Exception as e:
        raise HTTPException(502, f"问答失败: {e}") from e


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
            c.chat_runner.stream_ephemeral(
                body.text,
                doc_paths=paths,
                primary_doc=primary,
                web_enabled=body.web_enabled,
            ),
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
            observation_allowed=body.observation_allowed,
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
        return StreamingResponse(
            c.chat_runner.replay_turn(turn), media_type="text/event-stream"
        )

    return StreamingResponse(
        c.chat_runner.stream_and_persist(
            body.text,
            conversation_id=cid,
            turn=turn,
            history=history,
            doc_paths=paths,
            primary_doc=primary,
            web_enabled=body.web_enabled,
        ),
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
    indexed = c.knowledge_writer.index_extracted_text(rel, text)
    c.repo.log_change(
        f"上传附件 {rel}",
        commit_msg=f"chore: changelog upload {file.filename}",
    )
    return {"attachment": rel, "indexed": indexed}


@router.get("/download")
async def download(path: str, request: Request):
    c = _c(request)
    norm = path.replace("\\", "/").lstrip("/")
    if norm.startswith(".kb/") or norm.startswith(".git/"):
        raise HTTPException(404, "文件不存在")
    try:
        data = c.repo.get_attachment(norm)
    except FileNotFoundError:
        raise HTTPException(404, "文件不存在")
    filename = norm.rsplit("/", 1)[-1]
    media = "text/markdown; charset=utf-8" if norm.lower().endswith(".md") else "application/octet-stream"
    return StreamingResponse(
        io.BytesIO(data),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/download-zip")
async def download_zip(path: str, request: Request):
    from app.backup.export_kb import build_directory_zip

    c = _c(request)
    norm = path.replace("\\", "/").strip("/")
    if not norm:
        raise HTTPException(400, "请指定目录")
    if c.repo.is_protected(norm):
        raise HTTPException(403, "禁止下载该目录")
    try:
        buf = io.BytesIO()
        base_name = build_directory_zip(c.repo.root, norm, buf)
        buf.seek(0)
    except FileNotFoundError:
        raise HTTPException(404, "目录不存在")
    except NotADirectoryError:
        raise HTTPException(400, "不是目录")
    filename = f"{base_name}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/tree")
async def tree(request: Request):
    return {"docs": _c(request).repo.list_tree()}


@router.post("/kb/import")
async def kb_import(
    request: Request,
    file: UploadFile = File(...),
    directory: str = Form(""),
    filename: str | None = Form(None),
):
    from app.engine.kb_tree_service import (
        KbPathExistsError,
        suggest_alternate_filename,
    )

    _, svc = _kb_tree_service(request)
    name = (filename or file.filename or "upload.bin").strip()
    data = await file.read()
    try:
        return svc.import_upload(directory=directory, filename=name, data=data)
    except KbPathExistsError as e:
        raise HTTPException(
            409,
            detail=_kb_path_exists_detail(
                e.rel_path, str(e), suggest_alternate_filename(name)
            ),
        ) from e
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/kb/move")
async def kb_move(body: KbMoveBody, request: Request):
    from app.engine.kb_tree_service import (
        KbPathExistsError,
        suggest_alternate_filename,
    )

    _, svc = _kb_tree_service(request)
    try:
        return svc.move(
            from_path=body.from_path,
            to_directory=body.to_directory,
            to_filename=body.to_filename,
        )
    except KbPathExistsError as e:
        raise HTTPException(
            409,
            detail=_kb_path_exists_detail(
                e.rel_path,
                str(e),
                suggest_alternate_filename(
                    body.to_filename or body.from_path.rsplit("/", 1)[-1]
                ),
            ),
        ) from e
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(404, "源路径不存在") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/kb/delete")
async def kb_delete(body: KbDeleteBody, request: Request):
    _, svc = _kb_tree_service(request)
    try:
        return svc.delete(body.path)
    except FileNotFoundError as e:
        raise HTTPException(404, "路径不存在") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


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
    norm_path = body.path.replace("\\", "/")
    if norm_path == "系统/记忆.md":
        sync = c.memory_service.import_manual_document(doc.meta, body.body, dry_run=True)
        if not sync.get("ok"):
            raise HTTPException(400, sync.get("message", "记忆同步失败"))
        c.repo.write_doc(body.path, doc.meta, body.body, commit_msg=f"edit: {body.path}")
        sync = c.memory_service.import_manual_document(doc.meta, body.body)
        if not sync.get("ok"):
            c.repo.write_doc(body.path, doc.meta, old_body, commit_msg=f"rollback: {body.path}")
            raise HTTPException(400, sync.get("message", "记忆同步失败"))
        c.knowledge_writer.drop_from_index([body.path])
    else:
        if old_body != body.body:
            affected_start, affected_end = diff_affected_range(old_body, body.body)
            c.knowledge_writer.save_edit(
                body.path,
                doc.meta,
                old_body,
                body.body,
                affected_start=affected_start,
                affected_end=affected_end,
                commit_msg=f"edit: {body.path}",
                changelog_line=f"用户编辑 {body.path}",
            )
        else:
            c.repo.write_doc(body.path, doc.meta, body.body, commit_msg=f"edit: {body.path}")
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
    return True


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
            raise HTTPException(400, "该问题类型已废弃，请重新发起写入")
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


@router.get("/conversations/{cid}/events")
async def list_conversation_events(
    cid: str,
    request: Request,
    after_event_id: str | None = None,
    limit: int = 50,
):
    c = _c(request)
    try:
        c.conversations.get(cid)
    except KeyError as e:
        raise HTTPException(404, "对话不存在") from e
    events = c.conversations.list_system_events(
        cid, after_event_id=after_event_id, limit=limit
    )
    return {"events": events}


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
async def summarize_conversation(cid: str, body: SummarizeBody, request: Request):
    c = _c(request)
    rel_path, path_err = KnowledgeWriter.resolve_location(body.model_dump())
    if path_err:
        raise HTTPException(400, path_err.get("summary") or path_err.get("error"))
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
            conv=conv,
            forced_rel_path=rel_path,
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
            cid,
            conversation_fts=c.conversation_fts,
            conversation_vector=c.conversation_vector,
            indexer=c.indexer,
            index_revision=c.index_revision,
        )
    except KeyError as e:
        raise HTTPException(404, "对话不存在") from e
    return {"ok": True}
