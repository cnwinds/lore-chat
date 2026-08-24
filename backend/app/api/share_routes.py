"""分享链接 API：主人侧管理与公开只读访问。"""

from __future__ import annotations

import secrets
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api.http_deps import container
from app.auth.passwords import hash_password, verify_password
from app.engine.share_snapshot import (
    build_public_conversation_payload,
    build_public_doc_payload,
    exp_to_iso,
    grant_ttl_for_share,
    load_conversation_for_share,
    load_conversation_snapshot,
    load_doc_body,
    snapshot_conversation,
    snapshot_doc_pinned,
    conversation_live_payload_ref,
    conversation_share_public_title,
    validate_shareable_doc_path,
)
from app.models.share_links import ShareLinkStore, build_share_url, public_options
from app.models.share_unlocks import ShareUnlockStore, unlock_ttl_for_share

router = APIRouter()

SHARE_UNLOCK_COOKIE = "lorechat_share_unlock"
SHARE_UNLOCK_HEADER = "X-Share-Unlock"
_PASSWORD_MIN = 4
_PASSWORD_MAX = 128


class ShareOptionsBody(BaseModel):
    pin_version: bool = True


class CreateShareBody(BaseModel):
    type: str = Field(..., pattern="^(conversation|doc)$")
    conversation_id: str | None = None
    path: str | None = None
    title: str | None = None
    ttl_sec: int | None = None
    message_ids: list[str] | None = None
    password: str | None = None
    options: ShareOptionsBody = Field(default_factory=ShareOptionsBody)


class UnlockShareBody(BaseModel):
    password: str = Field(..., min_length=_PASSWORD_MIN, max_length=_PASSWORD_MAX)


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


def _normalize_password(raw: str | None) -> str | None:
    if raw is None:
        return None
    pw = raw.strip()
    if not pw:
        return None
    if len(pw) < _PASSWORD_MIN or len(pw) > _PASSWORD_MAX:
        raise HTTPException(
            400,
            f"password length must be {_PASSWORD_MIN}–{_PASSWORD_MAX}",
        )
    return pw


def _link_to_dict(link, *, url: str | None = None) -> dict:
    out = {
        "share_id": link.share_id,
        "type": link.type,
        "title": link.title,
        "created_at": link.created_at,
        "exp": exp_to_iso(link.exp),
        "revoked": link.revoked,
        "view_count": link.view_count,
        "last_viewed_at": link.last_viewed_at,
        "recent_views": list(link.recent_views),
        "options": public_options(link.options if isinstance(link.options, dict) else {}),
    }
    if url:
        out["url"] = url
    return out


def _password_hash_of(link) -> str | None:
    opts = link.options if isinstance(link.options, dict) else {}
    h = opts.get("password_hash")
    return str(h) if h else None


def _with_password(options: dict, password: str | None) -> dict:
    if not password:
        return options
    out = dict(options)
    out["has_password"] = True
    out["password_hash"] = hash_password(password)
    return out


def _unlock_id_from_request(request: Request) -> str | None:
    header = (request.headers.get(SHARE_UNLOCK_HEADER) or "").strip()
    if header:
        return header
    cookie = (request.cookies.get(SHARE_UNLOCK_COOKIE) or "").strip()
    return cookie or None


def _has_valid_unlock(request: Request, share_id: str, *, now: float) -> bool:
    uid = _unlock_id_from_request(request)
    if not uid:
        return False
    unlock = ShareUnlockStore(container(request).settings.kb_path).resolve(uid, now=now)
    return unlock is not None and unlock.share_id == share_id


@router.post("/shares")
async def create_share(body: CreateShareBody, request: Request):
    c = container(request)
    store = ShareLinkStore(c.settings.kb_path)
    public_base = _require_public_base_url(request)
    shares_dir = store.shares_dir
    share_id = secrets.token_urlsafe(18)
    password = _normalize_password(body.password)

    if body.type == "conversation":
        cid = (body.conversation_id or "").strip()
        if not cid:
            raise HTTPException(400, "conversation_id required")
        try:
            conv = c.conversations.get(cid)
        except KeyError as e:
            raise HTTPException(404, "对话不存在") from e
        pin_version = body.options.pin_version
        message_ids = body.message_ids
        if message_ids and not pin_version:
            raise HTTPException(
                400,
                "跟随更新的分享不支持消息区间，请使用全部消息或改为快照分享",
            )
        try:
            if pin_version:
                payload_ref = snapshot_conversation(
                    conv,
                    shares_dir=shares_dir,
                    share_id=share_id,
                    message_ids=message_ids,
                )
            else:
                payload_ref = conversation_live_payload_ref(cid)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        title = (body.title or conv.get("title") or "未命名对话").strip()
        options: dict = {
            "pin_version": pin_version,
            "conversation_id": cid,
        }
        if message_ids and pin_version:
            snap = load_conversation_snapshot(c.settings.kb_path, payload_ref)
            options["message_ids"] = [
                str(m.get("id"))
                for m in (snap.get("messages") or [])
                if isinstance(m, dict) and m.get("id")
            ]
            options["message_count"] = len(options["message_ids"])
        options = _with_password(options, password)
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
        if body.message_ids:
            raise HTTPException(400, "message_ids only allowed for conversation shares")
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
            c.repo.read_doc(norm)
            default_title = norm.split("/")[-1] or norm
        except FileNotFoundError as e:
            raise HTTPException(404, "文档不存在") from e
        title = (body.title or default_title).strip()
        options = _with_password(
            {"pin_version": pin_version, "source_path": norm},
            password,
        )
        link = store.create(
            type="doc",
            title=title,
            payload_ref=payload_ref,
            ttl_sec=body.ttl_sec,
            options=options,
            share_id=share_id,
        )

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


@router.post("/share/{share_id}/unlock")
async def unlock_public_share(
    share_id: str, body: UnlockShareBody, request: Request, response: Response
):
    c = container(request)
    store = ShareLinkStore(c.settings.kb_path)
    now = time.time()
    link, status = store.resolve_public(share_id, now=now, increment_view=False)
    if status == "expired":
        raise HTTPException(410, "分享链接已过期")
    if link is None:
        raise HTTPException(404, "分享链接不存在或已失效")
    pw_hash = _password_hash_of(link)
    if not pw_hash:
        raise HTTPException(400, "此分享未设置访问密码")
    if not verify_password(body.password.strip(), pw_hash):
        raise HTTPException(
            401,
            detail={"code": "SHARE_PASSWORD_INVALID", "message": "密码错误"},
        )
    ttl = unlock_ttl_for_share(link.exp, now=now)
    unlock_id = ShareUnlockStore(c.settings.kb_path).issue(
        share_id, ttl_sec=ttl, now=now
    )
    response.set_cookie(
        key=SHARE_UNLOCK_COOKIE,
        value=unlock_id,
        httponly=True,
        samesite="lax",
        # 按分享路径隔离，避免多分享共用一个 Cookie 互相覆盖
        path=f"/api/share/{share_id}",
        max_age=ttl,
    )
    return {"ok": True, "unlock_token": unlock_id, "ttl_sec": ttl}


@router.get("/share/{share_id}")
async def get_public_share(share_id: str, request: Request):
    c = container(request)
    store = ShareLinkStore(c.settings.kb_path)
    now = time.time()
    # 先不记访问量：密码门 401 不计次
    link, status = store.resolve_public(share_id, now=now, increment_view=False)
    if status == "expired":
        raise HTTPException(410, "分享链接已过期")
    if link is None:
        raise HTTPException(404, "分享链接不存在或已失效")

    if _password_hash_of(link) and not _has_valid_unlock(request, share_id, now=now):
        raise HTTPException(
            401,
            detail={
                "code": "SHARE_PASSWORD_REQUIRED",
                "message": "需要访问密码",
            },
        )

    public_base = (c.settings.public_base_url or "").strip()
    if not public_base:
        public_base = str(request.base_url).rstrip("/")
    grant_ttl = grant_ttl_for_share(link.exp, now=now)
    exp_iso = exp_to_iso(link.exp)

    try:
        if link.type == "conversation":
            snapshot = load_conversation_for_share(
                link,
                kb_path=c.settings.kb_path,
                conversations=c.conversations,
            )
            payload = build_public_conversation_payload(
                snapshot,
                title=conversation_share_public_title(link, snapshot),
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

    # 仅在成功组装公开 payload 后计次（密码 401 / 内容缺失 404 不计）
    referer = request.headers.get("referer") or request.headers.get("Referer")
    store.resolve_public(share_id, now=now, increment_view=True, referer=referer)
    return payload
