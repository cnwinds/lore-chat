"""角色知识卡 HTTP 接口。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.http_deps import container
from app.engine.memory.cards import OWNER_SCOPE, parse_scope, persona_scope, role_scope
from app.engine.memory.persona_history import PersonaRollbackError
from app.engine.roles import VISIBILITY_HIDDEN

router = APIRouter(tags=["cards"])


class EditCardBody(BaseModel):
    statement: str = Field(min_length=1)


def _cards(request: Request):
    return container(request).knowledge_cards


def _persona_history(request: Request):
    return container(request).persona_history


def _roles(request: Request):
    return container(request).roles


def _validate_scope(request: Request, scope: str) -> str:
    try:
        kind, subject_id = parse_scope(scope)
    except ValueError as e:
        raise HTTPException(400, "scope 无效") from e
    roles = _roles(request)
    if kind == "role":
        try:
            role = roles.get(subject_id)
        except KeyError as e:
            raise HTTPException(404, "角色不存在") from e
        if role.get("visibility") == VISIBILITY_HIDDEN:
            raise HTTPException(404, "角色不存在")
        return role_scope(subject_id)
    try:
        roles.get_persona(subject_id)
    except KeyError as e:
        raise HTTPException(404, "人设不存在") from e
    return persona_scope(subject_id)


def _validate_growth_scope(request: Request, scope: str) -> str:
    if scope == "owner":
        return OWNER_SCOPE
    return _validate_scope(request, scope)


@router.get("/cards/growth")
def list_card_growth(scope: str, request: Request, limit: int = 50):
    validated = _validate_growth_scope(request, scope)
    lim = max(1, min(int(limit), 200))
    entries = _cards(request).growth_entries(validated, limit=lim)
    return {"scope": validated, "entries": entries}


@router.get("/cards")
def list_cards(scope: str, request: Request):
    validated = _validate_scope(request, scope)
    svc = _cards(request)
    cards = svc.list_panel(validated)
    counts = svc.panel_counts(validated)
    return {
        "scope": validated,
        "cards": cards,
        "count": counts["count"],
        "faded_count": counts["faded_count"],
    }


@router.post("/cards/{card_id}/restore")
def restore_card(card_id: str, request: Request, scope: str):
    validated = _validate_scope(request, scope)
    out = _cards(request).restore(validated, card_id)
    if not out.get("ok"):
        raise HTTPException(400, detail=out.get("message") or out.get("error"))
    return out


@router.patch("/cards/{card_id}")
def edit_card(card_id: str, body: EditCardBody, request: Request, scope: str):
    validated = _validate_scope(request, scope)
    out = _cards(request).edit(validated, card_id, body.statement)
    if not out.get("ok"):
        raise HTTPException(400, detail=out.get("message") or out.get("error"))
    return out


@router.post("/cards/{card_id}/forget")
def forget_card(card_id: str, request: Request, scope: str):
    validated = _validate_scope(request, scope)
    out = _cards(request).forget(validated, card_id)
    if not out.get("ok"):
        raise HTTPException(400, detail=out.get("message") or out.get("error"))
    return out


@router.post("/cards/{card_id}/confirm")
def confirm_card(card_id: str, request: Request, scope: str):
    validated = _validate_scope(request, scope)
    out = _cards(request).confirm(validated, card_id)
    if not out.get("ok"):
        raise HTTPException(400, detail=out.get("message") or out.get("error"))
    return out


@router.post("/cards/{card_id}/reject")
def reject_card(card_id: str, request: Request, scope: str):
    validated = _validate_scope(request, scope)
    out = _cards(request).reject(validated, card_id)
    if not out.get("ok"):
        raise HTTPException(400, detail=out.get("message") or out.get("error"))
    return out


@router.get("/cards/persona/revisions")
def list_persona_revisions(scope: str, request: Request, limit: int = 30):
    validated = _validate_scope(request, scope)
    lim = max(1, min(int(limit), 100))
    revisions = _persona_history(request).list(validated, limit=lim)
    return {"scope": validated, "revisions": revisions}


@router.post("/cards/persona/revisions/{revision_id}/rollback")
def rollback_persona_revision(revision_id: str, request: Request, scope: str):
    validated = _validate_scope(request, scope)
    try:
        return _persona_history(request).rollback(validated, revision_id)
    except PersonaRollbackError as e:
        if e.code == "not_found":
            raise HTTPException(404, detail=e.message) from e
        if e.code == "invalid":
            raise HTTPException(400, detail=e.message) from e
        raise HTTPException(409, detail=e.message) from e


@router.post("/cards/proposals/{proposal_id}/accept")
def accept_card_proposal(proposal_id: str, request: Request, scope: str):
    validated = _validate_scope(request, scope)
    out = _cards(request).accept_proposal(validated, proposal_id)
    if not out.get("ok"):
        err = out.get("error")
        if err == "not_found":
            raise HTTPException(404, detail="提议不存在")
        raise HTTPException(400, detail="提议已处理")
    return out


@router.post("/cards/proposals/{proposal_id}/dismiss")
def dismiss_card_proposal(proposal_id: str, request: Request, scope: str):
    validated = _validate_scope(request, scope)
    out = _cards(request).dismiss_proposal(validated, proposal_id)
    if not out.get("ok"):
        err = out.get("error")
        if err == "not_found":
            raise HTTPException(404, detail="提议不存在")
        raise HTTPException(400, detail="提议已处理")
    return out
