from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.http_deps import (
    MergeBody,
    ResolveMergeSourcesBody,
    container,
    merge_session_view,
)

router = APIRouter()


@router.post("/docs/merge")
async def merge_docs(body: MergeBody, request: Request):
    c = container(request)
    result = c.merge_workflow.merge_documents(
        body.paths,
        instruction=body.instruction,
        order=body.order,
        title_hint=body.title,
        merge_sessions=c.merge_sessions,
    )
    return result.__dict__


@router.get("/docs/merge/active")
async def get_active_merge(path: str, request: Request):
    c = container(request)
    session = c.merge_sessions.find_active_by_path(path)
    if not session:
        raise HTTPException(404, "未找到进行中的合并会话")
    return merge_session_view(c, session)


@router.get("/docs/merge/{merge_id}")
async def get_merge(merge_id: str, request: Request):
    c = container(request)
    try:
        session = c.merge_sessions.get(merge_id)
    except KeyError as e:
        raise HTTPException(404, "合并会话不存在") from e
    return merge_session_view(c, session)


@router.post("/docs/merge/{merge_id}/regenerate")
async def regenerate_merge(merge_id: str, request: Request):
    c = container(request)
    try:
        result = c.merge_workflow.regenerate_merge(
            merge_id, merge_sessions=c.merge_sessions
        )
    except KeyError as e:
        raise HTTPException(404, "合并会话不存在") from e
    return result.__dict__


@router.post("/docs/merge/{merge_id}/accept")
async def accept_merge(merge_id: str, request: Request):
    c = container(request)
    try:
        result = c.merge_workflow.accept_merge(
            merge_id, merge_sessions=c.merge_sessions
        )
    except KeyError as e:
        raise HTTPException(404, "合并会话不存在") from e
    return result.__dict__


@router.post("/docs/merge/{merge_id}/reject")
async def reject_merge(merge_id: str, request: Request):
    c = container(request)
    try:
        result = c.merge_workflow.reject_merge(
            merge_id, merge_sessions=c.merge_sessions
        )
    except KeyError as e:
        raise HTTPException(404, "合并会话不存在") from e
    return result.__dict__


@router.post("/docs/merge/{merge_id}/resolve-sources")
async def resolve_merge_sources(
    merge_id: str, body: ResolveMergeSourcesBody, request: Request
):
    c = container(request)
    try:
        result = c.merge_workflow.resolve_merge_sources(
            merge_id,
            body.delete_paths,
            merge_sessions=c.merge_sessions,
        )
    except KeyError as e:
        raise HTTPException(404, "合并会话不存在") from e
    return result.__dict__
