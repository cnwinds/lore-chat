"""角色相关 Agent 工具。"""

from __future__ import annotations


class RoleTools:
    def __init__(self, roles, conversations=None) -> None:
        self.roles = roles
        self.conversations = conversations

    def _get_role_id(self, args: dict, conversation_id: str | None = None) -> str:
        """从 args 获取 role_id，未提供时使用当前会话角色 ID。"""
        role_id = args.get("role_id")
        if role_id:
            return str(role_id).strip()
        if conversation_id and self.conversations:
            return self.conversations.get_role_id(conversation_id)
        raise ValueError("未指定 role_id 且当前会话无关联角色")

    def create_role(self, args: dict) -> dict:
        if self.roles is None:
            return {
                "summary": "角色系统不可用",
                "sources": [],
                "error": "roles unavailable",
            }
        name = str(args.get("name") or "").strip()
        system_prompt = str(args.get("system_prompt") or "")
        avatar = args.get("avatar")
        if avatar is not None:
            avatar = str(avatar).strip() or None
        try:
            role = self.roles.create(
                name=name,
                system_prompt=system_prompt,
                avatar=avatar,
            )
        except ValueError as e:
            return {
                "summary": str(e),
                "sources": [],
                "error": str(e),
            }
        return {
            "summary": f"已创建角色「{role['name']}」（id={role['id']}）",
            "sources": [],
            "role": role,
        }

    def update_role(self, args: dict, conversation_id: str | None = None) -> dict:
        if self.roles is None:
            return {"summary": "角色系统不可用", "sources": [], "error": "roles unavailable"}
        try:
            role_id = self._get_role_id(args, conversation_id)
            default_id = self.roles.default_id()
            name = args.get("name")
            if name is not None:
                name = str(name).strip()
            avatar = args.get("avatar")
            if avatar is not None:
                avatar = str(avatar).strip() or None
            system_prompt = args.get("system_prompt")
            if system_prompt is not None:
                system_prompt = str(system_prompt)
            role = self.roles.update(
                role_id=role_id,
                name=name,
                avatar=avatar,
                system_prompt=system_prompt,
            )
            return {
                "summary": f"已更新角色「{role['name']}」",
                "sources": [],
                "role": role,
            }
        except (ValueError, KeyError) as e:
            return {"summary": str(e), "sources": [], "error": str(e)}

    def list_role_schedules(self, args: dict, conversation_id: str | None = None) -> dict:
        if self.roles is None:
            return {"summary": "角色系统不可用", "sources": [], "error": "roles unavailable"}
        try:
            role_id = self._get_role_id(args, conversation_id)
            schedules = self.roles.schedules.list_for_role(role_id)
            return {
                "summary": f"角色 {role_id} 有 {len(schedules)} 个定时任务",
                "sources": [],
                "schedules": schedules,
            }
        except (ValueError, KeyError) as e:
            return {"summary": str(e), "sources": [], "error": str(e)}

    def _timing_from_args(self, args: dict) -> tuple[dict | None, float | None]:
        timing = args.get("timing")
        if isinstance(timing, dict):
            return timing, args.get("interval_hours")
        hours = args.get("interval_hours")
        if hours is not None:
            return None, float(hours)
        return None, None

    def create_role_schedule(self, args: dict, conversation_id: str | None = None) -> dict:
        if self.roles is None:
            return {"summary": "角色系统不可用", "sources": [], "error": "roles unavailable"}
        try:
            role_id = self._get_role_id(args, conversation_id)
            prompt = str(args.get("prompt") or "").strip()
            enabled = bool(args.get("enabled", True))
            timing, hours = self._timing_from_args(args)
            if timing is None and hours is None:
                raise ValueError("请提供 timing 或 interval_hours")
            schedule = self.roles.schedules.create(
                role_id=role_id,
                prompt=prompt,
                interval_hours=hours,
                timing=timing,
                enabled=enabled,
            )
            summary = schedule.get("timing_summary") or "已创建定时任务"
            return {
                "summary": f"已为角色 {role_id} 创建例行任务：{summary}",
                "sources": [],
                "schedule": schedule,
            }
        except (ValueError, KeyError) as e:
            return {"summary": str(e), "sources": [], "error": str(e)}

    def update_role_schedule(self, args: dict) -> dict:
        if self.roles is None:
            return {"summary": "角色系统不可用", "sources": [], "error": "roles unavailable"}
        try:
            schedule_id = str(args.get("schedule_id") or "").strip()
            if not schedule_id:
                raise ValueError("缺少 schedule_id")
            prompt = args.get("prompt")
            if prompt is not None:
                prompt = str(prompt).strip()
            interval_hours = args.get("interval_hours")
            if interval_hours is not None:
                interval_hours = float(interval_hours)
            enabled = args.get("enabled")
            if enabled is not None:
                enabled = bool(enabled)
            timing = args.get("timing")
            if timing is not None and not isinstance(timing, dict):
                raise ValueError("timing 须为对象")
            schedule = self.roles.schedules.update(
                schedule_id=schedule_id,
                prompt=prompt,
                interval_hours=interval_hours,
                timing=timing if isinstance(timing, dict) else None,
                enabled=enabled,
            )
            summary = schedule.get("timing_summary") or schedule_id
            return {
                "summary": f"已更新例行任务 {schedule_id}（{summary}）",
                "sources": [],
                "schedule": schedule,
            }
        except (ValueError, KeyError) as e:
            return {"summary": str(e), "sources": [], "error": str(e)}

    def delete_role_schedule(self, args: dict) -> dict:
        if self.roles is None:
            return {"summary": "角色系统不可用", "sources": [], "error": "roles unavailable"}
        try:
            schedule_id = str(args.get("schedule_id") or "").strip()
            if not schedule_id:
                raise ValueError("缺少 schedule_id")
            self.roles.schedules.delete(schedule_id)
            return {
                "summary": f"已删除定时任务 {schedule_id}",
                "sources": [],
            }
        except (ValueError, KeyError) as e:
            return {"summary": str(e), "sources": [], "error": str(e)}

    def finalize_role_onboarding(self, args: dict, conversation_id: str | None = None) -> dict:
        if self.roles is None:
            return {"summary": "角色系统不可用", "sources": [], "error": "roles unavailable"}
        try:
            role_id = self._get_role_id(args, conversation_id)
            default_id = self.roles.default_id()
            if role_id == default_id:
                return {
                    "summary": "默认角色无需引导",
                    "sources": [],
                    "error": "default role no onboarding",
                }
            system_prompt = str(args.get("system_prompt") or "").strip()
            if not system_prompt:
                raise ValueError("完成引导必须提供 system_prompt")
            role = self.roles.update(
                role_id=role_id,
                system_prompt=system_prompt,
                onboarding_status="completed",
            )
            schedules_arg = args.get("schedules")
            created_schedules = []
            if schedules_arg and isinstance(schedules_arg, list):
                for sched in schedules_arg:
                    if not isinstance(sched, dict):
                        continue
                    prompt = str(sched.get("prompt") or "").strip()
                    if not prompt:
                        continue
                    timing = sched.get("timing") if isinstance(sched.get("timing"), dict) else None
                    hours = sched.get("interval_hours")
                    if hours is not None:
                        hours = float(hours)
                    enabled = bool(sched.get("enabled", True))
                    created = self.roles.schedules.create(
                        role_id=role_id,
                        prompt=prompt,
                        interval_hours=hours,
                        timing=timing,
                        enabled=enabled,
                    )
                    created_schedules.append(created)
            summary_parts = [f"已完成角色「{role['name']}」的引导"]
            if created_schedules:
                summary_parts.append(f"，并创建了 {len(created_schedules)} 个定时任务")
            return {
                "summary": "".join(summary_parts),
                "sources": [],
                "role": role,
                "schedules": created_schedules,
            }
        except (ValueError, KeyError) as e:
            return {"summary": str(e), "sources": [], "error": str(e)}
