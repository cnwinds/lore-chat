from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.api.http_deps import container

router = APIRouter()


class ConfirmPreceptsBody(BaseModel):
    body: str | None = None


@router.get("/precepts/upgrade")
async def precepts_upgrade_status(request: Request):
    return container(request).precepts_upgrade.status().as_dict()


@router.post("/precepts/upgrade/propose")
async def precepts_upgrade_propose(request: Request):
    return container(request).precepts_upgrade.propose().as_dict()


@router.post("/precepts/upgrade/confirm")
async def precepts_upgrade_confirm(body: ConfirmPreceptsBody, request: Request):
    try:
        return container(request).precepts_upgrade.confirm(body.body).as_dict()
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/precepts/upgrade/dismiss")
async def precepts_upgrade_dismiss(request: Request):
    return container(request).precepts_upgrade.dismiss().as_dict()


@router.post("/precepts/upgrade/use-official")
async def precepts_upgrade_use_official(request: Request):
    return container(request).precepts_upgrade.use_official().as_dict()
