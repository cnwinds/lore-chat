from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.deps import apply_settings

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/settings")
def get_settings(request: Request) -> dict[str, Any]:
    return request.app.state.settings_store.public_dict()


@router.put("/settings")
def put_settings(body: dict[str, Any], request: Request) -> dict[str, Any]:
    store = request.app.state.settings_store
    try:
        new_settings = store.update(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    apply_settings(request.app.state.container, new_settings)
    return store.public_dict()
