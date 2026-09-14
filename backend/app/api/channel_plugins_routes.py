"""主人侧聊天通道实例 CRUD（Cookie）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.api.http_deps import container
from app.engine.open_api import OpenApiError

router = APIRouter(prefix="/channel-plugins")


class CreateInstanceBody(BaseModel):
    type_id: str
    name: str
    persona_id: str | None = None
    persona_name: str | None = None
    persona_prompt: str = ""
    persona_avatar: str | None = None
    config: dict[str, Any] | None = None
    secrets: dict[str, Any] | None = None
    enabled: bool = True


class PatchInstanceBody(BaseModel):
    name: str | None = None
    persona_id: str | None = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None
    secrets: dict[str, Any] | None = None


class PersonaBody(BaseModel):
    name: str
    system_prompt: str = ""
    avatar: str | None = None
    from_role_id: str | None = None


class PersonaPatchBody(BaseModel):
    name: str | None = None
    system_prompt: str | None = None
    avatar: str | None = None


def _raise(err: OpenApiError) -> None:
    raise HTTPException(
        err.status,
        detail={"code": err.code, "message": str(err)},
    ) from err


@router.get("/types")
async def list_types(request: Request):
    return {"types": container(request).open_api.list_types()}


@router.get("/instances")
async def list_instances(request: Request):
    return {"instances": container(request).open_api.list_instances()}


@router.post("/instances")
async def create_instance(body: CreateInstanceBody, request: Request):
    try:
        return container(request).open_api.create_instance(
            type_id=body.type_id,
            name=body.name,
            persona_id=body.persona_id,
            persona_name=body.persona_name,
            persona_prompt=body.persona_prompt,
            persona_avatar=body.persona_avatar,
            config=body.config,
            secrets=body.secrets,
            enabled=body.enabled,
        )
    except KeyError as e:
        raise HTTPException(404, "人设不存在") from e
    except OpenApiError as e:
        _raise(e)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.patch("/instances/{instance_id}")
async def update_instance(
    instance_id: str, body: PatchInstanceBody, request: Request
):
    try:
        return container(request).open_api.update_instance(
            instance_id,
            name=body.name,
            persona_id=body.persona_id,
            enabled=body.enabled,
            config=body.config,
            secrets=body.secrets,
        )
    except KeyError as e:
        raise HTTPException(404, "通道不存在") from e
    except OpenApiError as e:
        _raise(e)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/instances/{instance_id}")
async def revoke_instance(instance_id: str, request: Request):
    try:
        return container(request).open_api.revoke_instance(instance_id)
    except KeyError as e:
        raise HTTPException(404, "通道不存在") from e


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


@router.get("/instances/{instance_id}/credential")
async def instance_credential(instance_id: str, request: Request):
    try:
        return container(request).open_api.instance_credential(instance_id)
    except KeyError as e:
        raise HTTPException(404, "通道不存在") from e


@router.get("/instances/{instance_id}/logs")
async def instance_logs(
    instance_id: str,
    request: Request,
    limit: int = 50,
    offset: int = 0,
):
    try:
        return container(request).open_api.instance_logs(
            instance_id, limit=limit, offset=offset
        )
    except KeyError as e:
        raise HTTPException(404, "通道不存在") from e


@router.get("/instances/{instance_id}/usage")
async def instance_usage(
    instance_id: str,
    request: Request,
    granularity: str = "day",
    start: str | None = None,
    end: str | None = None,
):
    try:
        return container(request).open_api.instance_usage(
            instance_id, granularity=granularity, start=start, end=end
        )
    except KeyError as e:
        raise HTTPException(404, "通道不存在") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
