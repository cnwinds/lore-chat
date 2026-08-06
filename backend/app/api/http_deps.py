"""HTTP 层共享：container 取用、DTO、聊天托盘规范化。"""

from __future__ import annotations

from typing import Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel


def container(request: Request):
    return request.app.state.container


def kb_tree_service(request: Request):
    from app.engine.kb_tree_service import KbTreeService

    c = container(request)
    return c, KbTreeService(c.repo, c.knowledge_writer, c.index_revision)


def kb_path_exists_detail(rel_path: str, message: str, suggested_filename: str) -> dict:
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


class DocContextItem(BaseModel):
    path: str
    kind: Literal["document", "skill_root"] = "document"


class ChatBody(BaseModel):
    text: str
    conversation_id: str | None = None
    client_message_id: str | None = None
    active_doc_path: str | None = None
    active_doc_paths: list[str] = []
    primary_doc_path: str | None = None
    doc_context: list[DocContextItem] = []
    web_enabled: bool = False
    attachments: list[str] = []
    observation_allowed: bool = True


class InjectBody(BaseModel):
    conversation_id: str
    text: str
    inject_id: str | None = None
    client_message_id: str | None = None
    doc_context: list[DocContextItem] = []
    primary_doc_path: str | None = None
    attachments: list[str] = []


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


class SummarizeBody(BaseModel):
    directory: str
    filename: str


class KbMoveBody(BaseModel):
    from_path: str
    to_directory: str
    to_filename: str | None = None


class KbDeleteBody(BaseModel):
    path: str


def normalize_chat_context(
    body: ChatBody,
    repo,
) -> tuple[list[dict[str, str]], list[str], list[str], str | None]:
    from app.engine.doc_context import (
        DocContextValidationError,
        missing_skill_roots,
        normalize_doc_context_items,
        parse_doc_context_for_api,
        split_doc_context,
    )

    if body.doc_context:
        try:
            items = parse_doc_context_for_api(
                [i.model_dump() for i in body.doc_context]
            )
        except DocContextValidationError as e:
            raise HTTPException(400, str(e)) from e
    else:
        paths = list(body.active_doc_paths)
        if body.active_doc_path and not paths:
            paths = [body.active_doc_path]
        items = normalize_doc_context_items(
            [{"path": p, "kind": "document"} for p in paths]
        )
    doc_paths, skill_roots = split_doc_context(items)
    if skill_roots:
        missing = missing_skill_roots(repo, skill_roots)
        if missing:
            raise HTTPException(
                400,
                f"以下 Skill 包不存在或缺少 SKILL.md：{', '.join(missing)}",
            )
    primary = body.primary_doc_path or body.active_doc_path
    if body.active_doc_path and body.active_doc_path not in doc_paths:
        if not doc_paths:
            doc_paths = [body.active_doc_path]
        if primary is None:
            primary = body.active_doc_path
    if primary is not None:
        if primary in skill_roots:
            raise HTTPException(400, "primary_doc_path 不能是 Skill 包路径")
        if primary not in doc_paths:
            raise HTTPException(400, "primary_doc_path 必须在文档托盘路径内")
    return items, doc_paths, skill_roots, primary


def merge_session_view(c, session: dict) -> dict:
    user_modified = False
    rel_path = session.get("new_path")
    if rel_path:
        try:
            body = c.repo.read_doc(rel_path).body
            user_modified = c.merge_sessions.user_modified(session["id"], body)
        except (FileNotFoundError, KeyError):
            user_modified = False
    return {"session": session, "user_modified": user_modified}
