"""主人侧开放接口管理（Cookie）：人设与 API Key。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.api.http_deps import container
from app.engine.open_api import OpenApiError

router = APIRouter(prefix="/open-api")


class PersonaBody(BaseModel):
    name: str
    system_prompt: str = ""
    avatar: str | None = None
    from_role_id: str | None = None


class PersonaPatchBody(BaseModel):
    name: str | None = None
    system_prompt: str | None = None
    avatar: str | None = None


class CreateKeyBody(BaseModel):
    name: str
    persona_id: str | None = None
    persona_name: str | None = None
    persona_prompt: str = ""
    persona_avatar: str | None = None


def _raise(err: OpenApiError) -> None:
    raise HTTPException(
        err.status,
        detail={"code": err.code, "message": str(err)},
    ) from err


@router.get("/personas")
async def list_personas(request: Request):
    return {"personas": container(request).open_api.list_personas()}


@router.post("/personas")
async def create_persona(body: PersonaBody, request: Request):
    svc = container(request).open_api
    try:
        if body.from_role_id:
            return svc.create_persona_from_role(body.from_role_id)
        return svc.create_persona(
            name=body.name,
            system_prompt=body.system_prompt,
            avatar=body.avatar,
        )
    except KeyError as e:
        raise HTTPException(404, "角色不存在") from e
    except OpenApiError as e:
        _raise(e)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.patch("/personas/{persona_id}")
async def update_persona(persona_id: str, body: PersonaPatchBody, request: Request):
    try:
        return container(request).open_api.update_persona(
            persona_id,
            name=body.name,
            system_prompt=body.system_prompt,
            avatar=body.avatar,
        )
    except KeyError as e:
        raise HTTPException(404, "人设不存在") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/personas/{persona_id}")
async def delete_persona(persona_id: str, request: Request):
    try:
        container(request).open_api.delete_persona(persona_id)
    except KeyError as e:
        raise HTTPException(404, "人设不存在") from e
    except OpenApiError as e:
        _raise(e)
    return {"ok": True}


@router.get("/keys")
async def list_keys(request: Request):
    return {"keys": container(request).open_api.list_keys()}


@router.post("/keys")
async def create_key(body: CreateKeyBody, request: Request):
    try:
        return container(request).open_api.create_key(
            name=body.name,
            persona_id=body.persona_id,
            persona_name=body.persona_name,
            persona_prompt=body.persona_prompt,
            persona_avatar=body.persona_avatar,
        )
    except KeyError as e:
        raise HTTPException(404, "人设不存在") from e
    except OpenApiError as e:
        _raise(e)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/keys/{key_id}")
async def revoke_key(key_id: str, request: Request):
    try:
        return container(request).open_api.revoke_key(key_id)
    except KeyError as e:
        raise HTTPException(404, "密钥不存在") from e
