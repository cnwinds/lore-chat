"""Phase 2：轻量记忆面板 API。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.http_deps import container

router = APIRouter(tags=["memory"])


class EditMemoryBody(BaseModel):
    statement: str = Field(min_length=1)


def _svc(request: Request):
    return container(request).memory_service


@router.get("/memory/facts")
def list_memory_facts(request: Request):
    return _svc(request).list_panel_facts()


@router.post("/memory/facts/{fact_id}/confirm")
def confirm_memory_fact(fact_id: str, request: Request):
    out = _svc(request).confirm_candidate(fact_id)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("message") or out.get("error"))
    return out


@router.post("/memory/facts/{fact_id}/reject")
def reject_memory_fact(fact_id: str, request: Request):
    out = _svc(request).reject_candidate(fact_id)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("message") or out.get("error"))
    return out


@router.patch("/memory/facts/{fact_id}")
def edit_memory_fact(fact_id: str, body: EditMemoryBody, request: Request):
    out = _svc(request).edit_fact(fact_id, body.statement)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("message") or out.get("error"))
    return out


@router.post("/memory/facts/{fact_id}/forget")
def forget_memory_fact(fact_id: str, request: Request):
    out = _svc(request).forget(fact_id=fact_id)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("message") or out.get("error"))
    return out
