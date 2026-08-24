"""分享链接 API：主人侧管理与公开只读访问。"""

from __future__ import annotations

import secrets
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.http_deps import container
from app.engine.share_snapshot import (
    build_public_conversation_payload,
    build_public_doc_payload,
    exp_to_iso,
    grant_ttl_for_share,
    load_conversation_snapshot,
    load_doc_body,
    snapshot_conversation,
    snapshot_doc_pinned,
    validate_shareable_doc_path,
)
from app.models.share_links import ShareLinkStore, build_share_url

router = APIRouter()


class ShareOptionsBody(BaseModel):
    pin_version: bool = True


class CreateShareBody(BaseModel):
    type: str = Field(..., pattern="^(conversation|doc)$")
    conversation_id: str | None = None
    path: str | None = None
    title: str | None = None
    ttl_sec: int | None = None
    options: ShareOptionsBody = Field(default_factory=ShareOptionsBody)


def _require_public_base_url(request: Request) -> str:
    base = (container(request).settings.public_base_url or "").strip()
    if not base:
        raise HTTPException(
            400,
            detail={
                "code": "PUBLIC_BASE_URL_REQUIRED",
                "message": "请先在设置中配置 Public Base URL 后再创建分享链接",
            },
        )
    return base


def _link_to_dict(link, *, url: str | None = None) -> dict:
    out = {
        "share_id": link.share_id,
        "type": link.type,
        "title": link.title,
        "created_at": link.created_at,
        "exp": exp_to_iso(link.exp),
        "revoked": link.revoked,
        "view_count": link.view_count,
        "options": link.options,
    }
    if url:
        out["url"] = url
    return out


@router.post("/shares")
async def create_share(body: CreateShareBody, request: Request):
    c = container(request)
    store = ShareLinkStore(c.settings.kb_path)
    public_base = _require_public_base_url(request)
    kb_path = c.settings.kb_path
    shares_dir = store.shares_dir
    share_id = secrets.token_urlsafe(18)

    if body.type == "conversation":
        cid = (body.conversation_id or "").strip()
        if not cid:
            raise HTTPException(400, "conversation_id required")
        try:
            conv = c.conversations.get(cid)
        except KeyError as e:
            raise HTTPException(404, "对话不存在") from e
        payload_ref = snapshot_conversation(
            conv, shares_dir=shares_dir, share_id=share_id
        )
        title = (body.title or conv.get("title") or "未命名对话").strip()
        options: dict = {}
        link = store.create(
            type="conversation",
            title=title,
            payload_ref=payload_ref,
            ttl_sec=body.ttl_sec,
            options=options,
            share_id=share_id,
        )
    else:
        raw_path = (body.path or "").strip()
        if not raw_path:
            raise HTTPException(400, "path required")
        try:
            norm = validate_shareable_doc_path(c.repo, raw_path)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        pin_version = body.options.pin_version
        if pin_version:
            payload_ref = snapshot_doc_pinned(
                c.repo, norm, shares_dir=shares_dir, share_id=share_id
            )
        else:
            payload_ref = norm
        try:
            doc = c.repo.read_doc(norm)
            default_title = norm.split("/")[-1] or norm
        except FileNotFoundError as e:
            raise HTTPException(404, "文档不存在") from e
        title = (body.title or default_title).strip()
        options = {"pin_version": pin_version, "source_path": norm}
        link = store.create(
            type="doc",
            title=title,
            payload_ref=payload_ref,
            ttl_sec=body.ttl_sec,
            options=options,
            share_id=share_id,
        )
        del doc  # title only

    url = build_share_url(public_base_url=public_base, share_id=link.share_id)
    return _link_to_dict(link, url=url)


@router.get("/shares")
async def list_shares(request: Request):
    store = ShareLinkStore(container(request).settings.kb_path)
    public_base = (container(request).settings.public_base_url or "").strip()
    items = []
    for link in store.list_all():
        url = (
            build_share_url(public_base_url=public_base, share_id=link.share_id)
            if public_base
            else None
        )
        items.append(_link_to_dict(link, url=url))
    return {"shares": items}


@router.delete("/shares/{share_id}")
async def revoke_share(share_id: str, request: Request):
    store = ShareLinkStore(container(request).settings.kb_path)
    if not store.revoke(share_id):
        raise HTTPException(404, "分享不存在")
    return {"ok": True}


@router.get("/share/{share_id}")
async def get_public_share(share_id: str, request: Request):
    c = container(request)
    store = ShareLinkStore(c.settings.kb_path)
    now = time.time()
    link, status = store.resolve_public(share_id, now=now, increment_view=True)
    if status == "expired":
        raise HTTPException(410, "分享链接已过期")
    if link is None:
        raise HTTPException(404, "分享链接不存在或已失效")
    public_base = (c.settings.public_base_url or "").strip()
    if not public_base:
        public_base = str(request.base_url).rstrip("/")
    grant_ttl = grant_ttl_for_share(link.exp, now=now)
    exp_iso = exp_to_iso(link.exp)

    try:
        if link.type == "conversation":
            snapshot = load_conversation_snapshot(c.settings.kb_path, link.payload_ref)
            payload = build_public_conversation_payload(
                snapshot,
                title=link.title,
                exp_iso=exp_iso,
                kb_path=c.settings.kb_path,
                public_base_url=public_base,
                grant_ttl_sec=grant_ttl,
            )
        elif link.type == "doc":
            body = load_doc_body(c.repo, c.settings.kb_path, link)
            payload = build_public_doc_payload(
                body,
                title=link.title,
                exp_iso=exp_iso,
                kb_path=c.settings.kb_path,
                public_base_url=public_base,
                grant_ttl_sec=grant_ttl,
            )
        else:
            raise HTTPException(404, "分享链接不存在或已失效")
    except (FileNotFoundError, ValueError, OSError):
        raise HTTPException(404, "分享链接不存在或已失效") from None
    return payload
