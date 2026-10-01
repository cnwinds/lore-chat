from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _overview_service(request: Request):
    container = request.app.state.container
    svc = getattr(container, "background_overview", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="background overview unavailable")
    return svc


@router.get("/background")
def get_background_overview(request: Request) -> dict:
    svc = _overview_service(request)
    return svc.overview()


@router.get("/background/status")
def get_background_status(request: Request) -> dict:
    svc = _overview_service(request)
    return svc.status()


@router.get("/background/calls")
def list_background_calls(
    request: Request, purpose: str, limit: int = 20
) -> dict:
    blog = request.app.state.container.background_call_log
    if blog is None:
        raise HTTPException(status_code=503, detail="background call log unavailable")
    return {"calls": blog.list_calls(purpose, limit=limit)}


@router.get("/background/calls/{call_id}")
def get_background_call(request: Request, call_id: int) -> dict:
    blog = request.app.state.container.background_call_log
    if blog is None:
        raise HTTPException(status_code=503, detail="background call log unavailable")
    row = blog.get_call(call_id)
    if row is None:
        raise HTTPException(status_code=404, detail="call not found")
    return row
