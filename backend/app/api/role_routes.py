"""Role management HTTP routes."""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.http_deps import get_kb_root, get_conversations, get_settings
from app.engine.roles import RoleStore, resolve_active_conversation, DEFAULT_ROLE_ID
from app.engine.conversations import ConversationsStore
from app.config import Settings

import uuid

router = APIRouter(prefix="/api/roles", tags=["roles"])


def get_role_store(kb_root=Depends(get_kb_root)) -> RoleStore:
    return RoleStore(kb_root)


# Request/Response models

class CreateRoleRequest(BaseModel):
    name: str
    avatar: str | None = None
    system_prompt: str | None = None


class UpdateRoleRequest(BaseModel):
    name: str | None = None
    avatar: str | None = None
    system_prompt: str | None = None


class CreateScheduleRequest(BaseModel):
    cron: str
    prompt: str
    enabled: bool = True


class UpdateScheduleRequest(BaseModel):
    cron: str | None = None
    prompt: str | None = None
    enabled: bool | None = None


# Routes

@router.get("")
def list_roles(store: Annotated[RoleStore, Depends(get_role_store)]):
    """List all roles."""
    roles = store.list_roles()
    return {"roles": roles}


@router.post("")
def create_role(
    req: CreateRoleRequest,
    store: Annotated[RoleStore, Depends(get_role_store)],
):
    """Create a new role."""
    role_id = str(uuid.uuid4())
    role = store.create_role(
        role_id=role_id,
        name=req.name,
        avatar=req.avatar,
        system_prompt=req.system_prompt,
    )
    return role


@router.get("/{role_id}")
def get_role(
    role_id: str,
    store: Annotated[RoleStore, Depends(get_role_store)],
):
    """Get role by ID."""
    role = store.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


@router.patch("/{role_id}")
def update_role(
    role_id: str,
    req: UpdateRoleRequest,
    store: Annotated[RoleStore, Depends(get_role_store)],
):
    """Update role."""
    role = store.update_role(
        role_id=role_id,
        name=req.name,
        avatar=req.avatar,
        system_prompt=req.system_prompt,
    )
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


@router.delete("/{role_id}")
def delete_role(
    role_id: str,
    store: Annotated[RoleStore, Depends(get_role_store)],
):
    """Delete role (cannot delete default role)."""
    success = store.delete_role(role_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot delete default role or role not found")
    return {"ok": True}


@router.post("/{role_id}/ensure-active")
def ensure_active_conversation(
    role_id: str,
    store: Annotated[RoleStore, Depends(get_role_store)],
    conversations: Annotated[ConversationsStore, Depends(get_conversations)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    """
    Resolve or create active conversation for a role.
    Returns conversation_id to switch to.
    """
    role = store.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    continuity_hours = getattr(settings, "continuity_idle_hours", 6.0)
    conversation_id = resolve_active_conversation(
        role_id=role_id,
        conversations_store=conversations,
        continuity_idle_hours=continuity_hours,
    )

    return {"conversation_id": conversation_id, "role_id": role_id}


# Schedules

@router.get("/{role_id}/schedules")
def list_role_schedules(
    role_id: str,
    store: Annotated[RoleStore, Depends(get_role_store)],
):
    """List schedules for a role."""
    role = store.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    schedules = store.list_schedules(role_id)
    return {"schedules": schedules}


@router.post("/{role_id}/schedules")
def create_role_schedule(
    role_id: str,
    req: CreateScheduleRequest,
    store: Annotated[RoleStore, Depends(get_role_store)],
):
    """Create schedule for a role."""
    role = store.get_role(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    schedule_id = str(uuid.uuid4())
    schedule = store.create_schedule(
        schedule_id=schedule_id,
        role_id=role_id,
        cron=req.cron,
        prompt=req.prompt,
        enabled=req.enabled,
    )
    return schedule


@router.patch("/{role_id}/schedules/{schedule_id}")
def update_role_schedule(
    role_id: str,
    schedule_id: str,
    req: UpdateScheduleRequest,
    store: Annotated[RoleStore, Depends(get_role_store)],
):
    """Update schedule."""
    schedule = store.get_schedule(schedule_id)
    if not schedule or schedule["role_id"] != role_id:
        raise HTTPException(status_code=404, detail="Schedule not found")

    updated = store.update_schedule(
        schedule_id=schedule_id,
        cron=req.cron,
        prompt=req.prompt,
        enabled=req.enabled,
    )
    return updated


@router.delete("/{role_id}/schedules/{schedule_id}")
def delete_role_schedule(
    role_id: str,
    schedule_id: str,
    store: Annotated[RoleStore, Depends(get_role_store)],
):
    """Delete schedule."""
    schedule = store.get_schedule(schedule_id)
    if not schedule or schedule["role_id"] != role_id:
        raise HTTPException(status_code=404, detail="Schedule not found")

    success = store.delete_schedule(schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")

    return {"ok": True}
