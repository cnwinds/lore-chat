"""角色 CRUD、忙碌态、定时任务与活跃线（ADR 2026-09-09）。"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from app.api.http_deps import container
from app.engine.role_onboarding import maybe_kickoff_role_onboarding

router = APIRouter()


class CreateRoleBody(BaseModel):
    name: str
    system_prompt: str = ""
    avatar: str | None = None


class UpdateRoleBody(BaseModel):
    name: str | None = None
    system_prompt: str | None = None
    avatar: str | None = None


class ScheduleTimingBody(BaseModel):
    kind: Literal[
        "interval", "hourly", "daily", "weekdays", "weekly", "monthly", "cron"
    ]
    interval_hours: float | None = Field(default=None, ge=0.5)
    hour: int | None = Field(default=None, ge=0, le=23)
    minute: int | None = Field(default=None, ge=0, le=59)
    weekdays: list[int] | None = None
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    cron: str | None = None


class CreateScheduleBody(BaseModel):
    prompt: str
    timing: ScheduleTimingBody | None = None
    interval_hours: float | None = Field(default=None, ge=0.5)
    enabled: bool = True

    @model_validator(mode="after")
    def _need_timing(self) -> CreateScheduleBody:
        if self.timing is None and self.interval_hours is None:
            raise ValueError("请提供 timing 或 interval_hours")
        return self


class UpdateScheduleBody(BaseModel):
    prompt: str | None = None
    timing: ScheduleTimingBody | None = None
    interval_hours: float | None = Field(default=None, ge=0.5)
    enabled: bool | None = None


def _timing_payload(timing: ScheduleTimingBody | None) -> dict[str, Any] | None:
    if timing is None:
        return None
    return timing.model_dump(exclude_none=True)


def _attach_role_list_fields(
    role: dict[str, Any],
    activity: dict[str, str],
    replies: dict[str, str],
) -> dict[str, Any]:
    return {
        **role,
        "last_active_at": activity.get(role["id"]),
        "last_reply_preview": replies.get(role["id"]),
    }


@router.get("/roles")
async def list_roles(request: Request):
    c = container(request)
    activity = c.conversations.last_active_at_by_role()
    replies = c.conversations.last_reply_preview_by_role()
    return {
        "roles": [
            _attach_role_list_fields(role, activity, replies)
            for role in c.roles.list_all()
        ]
    }


@router.post("/roles")
async def create_role(body: CreateRoleBody, request: Request):
    c = container(request)
    try:
        role = c.roles.create(
            name=body.name,
            system_prompt=body.system_prompt,
            avatar=body.avatar,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if role.get("onboarding_status") == "active":
        maybe_kickoff_role_onboarding(c, role["id"])
    return role


@router.get("/roles/busy")
async def list_busy_roles(request: Request):
    """有 running turn 的角色 id 列表。"""
    return {"role_ids": container(request).conversations.list_busy_role_ids()}


@router.get("/roles/{role_id}")
async def get_role(role_id: str, request: Request):
    c = container(request)
    try:
        role = c.roles.get(role_id)
    except KeyError as e:
        raise HTTPException(404, "角色不存在") from e
    return _attach_role_list_fields(
        role,
        c.conversations.last_active_at_by_role(),
        c.conversations.last_reply_preview_by_role(),
    )


@router.patch("/roles/{role_id}")
async def update_role(role_id: str, body: UpdateRoleBody, request: Request):
    c = container(request)
    try:
        return c.roles.update(
            role_id,
            name=body.name,
            system_prompt=body.system_prompt,
            avatar=body.avatar,
        )
    except KeyError as e:
        raise HTTPException(404, "角色不存在") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/roles/{role_id}")
async def delete_role(role_id: str, request: Request):
    c = container(request)
    try:
        c.roles.get(role_id)
    except KeyError as e:
        raise HTTPException(404, "角色不存在") from e
    try:
        default_id = c.roles.default_id()
        if role_id == default_id:
            raise ValueError("不能删除默认角色")
        moved = c.conversations.reassign_role(role_id, default_id)
        c.roles.delete(role_id)
    except KeyError as e:
        raise HTTPException(404, "角色不存在") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "reassigned_conversations": moved}


@router.post("/roles/{role_id}/ensure-active")
async def ensure_active_conversation(role_id: str, request: Request):
    c = container(request)
    try:
        c.roles.get(role_id)
    except KeyError as e:
        raise HTTPException(404, "角色不存在") from e
    cid, created = c.conversations.ensure_active_conversation(
        role_id,
        idle_hours=float(c.settings.continuity_idle_hours),
    )
    maybe_kickoff_role_onboarding(c, role_id)
    return {
        "conversation_id": cid,
        "role_id": role_id,
        "created": created,
    }


@router.get("/roles/{role_id}/timeline")
async def get_role_timeline(
    role_id: str,
    request: Request,
    include_messages: bool = True,
    limit: int = 5,
    before_created_at: str | None = None,
    before_id: str | None = None,
):
    """角色统一时间线（分页）：默认最近若干段；before_* 取更早。

    首屏不传 before → 最近 ``limit`` 段（含 tip 空壳）；上滚传最旧段的
    created_at/id 作为 before 游标。
    """
    c = container(request)
    try:
        c.roles.get(role_id)
    except KeyError as e:
        raise HTTPException(404, "角色不存在") from e
    tip_id: str | None
    created = False
    if before_created_at:
        # 续载只读：禁止 ensure（否则窗口外会新建 tip / 关段抽取）
        tip_id = c.conversations.find_active_conversation_id(
            role_id,
            idle_hours=float(c.settings.continuity_idle_hours),
        ) or c.conversations._latest_conversation_id(role_id)
    else:
        tip_id, created = c.conversations.ensure_active_conversation(
            role_id,
            idle_hours=float(c.settings.continuity_idle_hours),
        )
        maybe_kickoff_role_onboarding(c, role_id)
    # 续载更早历史时不要反复 ensure 干扰；仍返回当前 tip id
    page_limit = max(1, min(int(limit or 5), 30))
    segments, has_more = c.conversations.list_timeline(
        role_id,
        include_messages=include_messages,
        limit=page_limit,
        before_created_at=before_created_at,
        before_id=before_id,
        tip_id=None if before_created_at else tip_id,
        only_with_messages=True,
    )
    return {
        "role_id": role_id,
        "tip_conversation_id": tip_id,
        "tip_created": created,
        "continuity_idle_hours": float(c.settings.continuity_idle_hours),
        "segments": segments,
        "has_more": has_more,
        "limit": page_limit,
    }


@router.post("/roles/{role_id}/new-topic")
async def open_role_new_topic(role_id: str, request: Request):
    """强制新话题：关上一 tip（记忆抽取）并新建空段。"""
    c = container(request)
    try:
        c.roles.get(role_id)
    except KeyError as e:
        raise HTTPException(404, "角色不存在") from e
    cid = c.conversations.open_new_topic(role_id)
    return {"conversation_id": cid, "role_id": role_id}


@router.get("/roles/{role_id}/schedules")
async def list_schedules(role_id: str, request: Request):
    c = container(request)
    try:
        c.roles.get(role_id)
    except KeyError as e:
        raise HTTPException(404, "角色不存在") from e
    return {"schedules": c.roles.schedules.list_for_role(role_id)}


@router.post("/roles/{role_id}/schedules")
async def create_schedule(role_id: str, body: CreateScheduleBody, request: Request):
    c = container(request)
    try:
        c.roles.get(role_id)
    except KeyError as e:
        raise HTTPException(404, "角色不存在") from e
    try:
        return c.roles.schedules.create(
            role_id,
            prompt=body.prompt,
            interval_hours=body.interval_hours,
            timing=_timing_payload(body.timing),
            enabled=body.enabled,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.patch("/roles/{role_id}/schedules/{schedule_id}")
async def update_schedule(
    role_id: str, schedule_id: str, body: UpdateScheduleBody, request: Request
):
    c = container(request)
    try:
        c.roles.get(role_id)
        owned = {
            s["id"]: s for s in c.roles.schedules.list_for_role(role_id)
        }
        if schedule_id not in owned:
            raise KeyError(schedule_id)
        return c.roles.schedules.update(
            schedule_id,
            prompt=body.prompt,
            interval_hours=body.interval_hours,
            timing=_timing_payload(body.timing),
            enabled=body.enabled,
        )
    except KeyError as e:
        raise HTTPException(404, "不存在") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/roles/{role_id}/schedules/{schedule_id}/runs")
async def list_schedule_runs(role_id: str, schedule_id: str, request: Request):
    c = container(request)
    try:
        c.roles.get(role_id)
        owned = {s["id"] for s in c.roles.schedules.list_for_role(role_id)}
        if schedule_id not in owned:
            raise KeyError(schedule_id)
    except KeyError as e:
        raise HTTPException(404, "不存在") from e
    return {
        "runs": c.conversations.list_role_schedule_runs(schedule_id),
    }


@router.delete("/roles/{role_id}/schedules/{schedule_id}")
async def delete_schedule(role_id: str, schedule_id: str, request: Request):
    c = container(request)
    try:
        c.roles.get(role_id)
        items = c.roles.schedules.list_for_role(role_id)
        if not any(s["id"] == schedule_id for s in items):
            raise KeyError(schedule_id)
        c.roles.schedules.delete(schedule_id)
    except KeyError as e:
        raise HTTPException(404, "不存在") from e
    return {"ok": True}
