"""角色相关 Agent 工具。"""

from __future__ import annotations

from app.engine.roles import VISIBILITY_HIDDEN, VISIBILITY_SIDEBAR


class RoleTools:
    def __init__(self, roles, conversations=None, delivery=None) -> None:
        self.roles = roles
        self.conversations = conversations
        self.delivery = delivery

    def _get_role_id(self, args: dict, conversation_id: str | None = None) -> str:
        """从 args 获取 role_id，未提供时使用当前会话角色 ID。"""
        role_id = args.get("role_id")
        if role_id:
            return str(role_id).strip()
        if conversation_id and self.conversations:
            return self.conversations.get_role_id(conversation_id)
        raise ValueError("未指定 role_id 且当前会话无关联角色")

    def _current_role_id(self, conversation_id: str | None) -> str | None:
        if not conversation_id or self.conversations is None:
            return None
        try:
            return self.conversations.get_role_id(conversation_id)
        except (KeyError, ValueError):
            return None

    def _busy_ids(self) -> set[str]:
        if self.conversations is None:
            return set()
        try:
            return set(self.conversations.list_busy_role_ids())
        except Exception:
            return set()

    def _role_payload(
        self,
        role: dict,
        current_role_id: str | None,
        *,
        busy_ids: set[str] | None = None,
    ) -> dict:
        rid = role["id"]
        try:
            schedule_count = len(self.roles.schedules.list_for_role(rid))
        except (KeyError, ValueError, AttributeError):
            schedule_count = 0
        prompt = (role.get("system_prompt") or "").strip()
        duty = prompt.splitlines()[0][:80] if prompt else ""
        return {
            "id": rid,
            "name": role["name"],
            "avatar": role.get("avatar"),
            "system_prompt": role.get("system_prompt") or "",
            "duty": duty,
            "busy": rid in (busy_ids or set()),
            "is_default": bool(role.get("is_default")),
            "is_current": bool(current_role_id and rid == current_role_id),
            "onboarding_status": role.get("onboarding_status") or "none",
            "sort_order": int(role.get("sort_order") or 0),
            "schedule_count": schedule_count,
            "created_at": role.get("created_at"),
            "updated_at": role.get("updated_at"),
        }

    @staticmethod
    def _match_roles_by_name(roles: list[dict], name: str) -> list[dict]:
        exact = [r for r in roles if r["name"] == name]
        if exact:
            return exact
        lowered = name.casefold()
        return [r for r in roles if str(r["name"]).casefold() == lowered]

    @staticmethod
    def _detail_summary(role: dict) -> str:
        flags = []
        if role.get("is_default"):
            flags.append("默认")
        if role.get("is_current"):
            flags.append("当前会话")
        suffix = f"（{'，'.join(flags)}）" if flags else ""
        return f"角色「{role['name']}」{suffix} id={role['id']}"

    def _sidebar_roles(self) -> list[dict]:
        try:
            return self.roles.list_all(visibility=VISIBILITY_SIDEBAR)
        except TypeError:
            return [
                role
                for role in self.roles.list_all()
                if (role.get("visibility") or VISIBILITY_SIDEBAR) != VISIBILITY_HIDDEN
            ]

    def _is_hidden(self, role: dict) -> bool:
        return (role.get("visibility") or VISIBILITY_SIDEBAR) == VISIBILITY_HIDDEN

    def list_roles(self, args: dict, conversation_id: str | None = None) -> dict:
        if self.roles is None:
            return {
                "summary": "角色系统不可用",
                "sources": [],
                "error": "roles unavailable",
            }
        current_role_id = self._current_role_id(conversation_id)
        busy_ids = self._busy_ids()
        role_id = str(args.get("role_id") or "").strip()
        name = str(args.get("name") or "").strip()

        if role_id:
            try:
                role = self.roles.get(role_id)
            except KeyError:
                return {
                    "summary": f"未找到 id 为 {role_id} 的角色",
                    "sources": [],
                    "error": "role not found",
                    "roles": [],
                }
            if self._is_hidden(role):
                return {
                    "summary": f"未找到 id 为 {role_id} 的角色",
                    "sources": [],
                    "error": "role not found",
                    "roles": [],
                }
            payload = self._role_payload(role, current_role_id, busy_ids=busy_ids)
            return {
                "summary": self._detail_summary(payload),
                "sources": [],
                "role": payload,
                "roles": [payload],
            }

        all_roles = self._sidebar_roles()
        if name:
            matched = self._match_roles_by_name(all_roles, name)
            if not matched:
                return {
                    "summary": f"未找到名为「{name}」的角色",
                    "sources": [],
                    "error": "role not found",
                    "roles": [],
                }
            payloads = [
                self._role_payload(r, current_role_id, busy_ids=busy_ids)
                for r in matched
            ]
            if len(payloads) == 1:
                return {
                    "summary": self._detail_summary(payloads[0]),
                    "sources": [],
                    "role": payloads[0],
                    "roles": payloads,
                }
            return {
                "summary": f"找到 {len(payloads)} 个名为「{name}」的角色",
                "sources": [],
                "roles": payloads,
            }

        payloads = [
            self._role_payload(r, current_role_id, busy_ids=busy_ids)
            for r in all_roles
        ]
        names = "、".join(p["name"] for p in payloads)
        return {
            "summary": f"共 {len(payloads)} 个角色：{names}",
            "sources": [],
            "roles": payloads,
        }

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

    def send_message(self, args: dict, conversation_id: str | None = None) -> dict:
        if self.delivery is None:
            return {
                "summary": "角色互通不可用",
                "sources": [],
                "error": "room delivery unavailable",
            }
        try:
            from_role_id = self._get_role_id({}, conversation_id)
            result = self.delivery.send_from_role(
                from_role_id=from_role_id,
                conversation_id=conversation_id,
                text=str(args.get("text") or ""),
                to_role_id=args.get("to_role_id"),
                to_role_name=args.get("to_role_name"),
                room_id=args.get("room_id"),
                mentions=args.get("mentions"),
                expect_reply=bool(args.get("expect_reply", True)),
            )
            return result
        except (ValueError, KeyError) as e:
            return {"summary": str(e), "sources": [], "error": str(e)}

    def list_rooms(self, args: dict, conversation_id: str | None = None) -> dict:
        if self.delivery is None:
            return {
                "summary": "角色互通不可用",
                "sources": [],
                "error": "room delivery unavailable",
            }
        del args
        try:
            role_id = self._get_role_id({}, conversation_id)
            rooms = self.delivery.list_rooms_for_role(role_id)
            return {
                "summary": f"当前角色参与 {len(rooms)} 个协作/群聊房间",
                "sources": [],
                "rooms": rooms,
            }
        except (ValueError, KeyError) as e:
            return {"summary": str(e), "sources": [], "error": str(e)}

    def create_room(self, args: dict, conversation_id: str | None = None) -> dict:
        if self.delivery is None:
            return {
                "summary": "角色互通不可用",
                "sources": [],
                "error": "room delivery unavailable",
            }
        try:
            current = self._get_role_id({}, conversation_id)
            ids: list[str] = []
            seen: set[str] = set()

            def _add(rid: str) -> None:
                if rid and rid not in seen:
                    seen.add(rid)
                    ids.append(rid)

            _add(current)
            for raw in args.get("role_ids") or []:
                _add(str(raw or "").strip())
            for raw in args.get("role_names") or []:
                role = self.delivery.resolve_target(
                    to_role_name=str(raw or ""), except_role_id=None
                )
                _add(role["id"])
            room = self.delivery.create_group(
                title=str(args.get("title") or ""),
                role_ids=ids,
            )
            return {
                "summary": (
                    f"已建群「{room['title']}」，"
                    f"conversation://{room['id']}"
                ),
                "sources": [],
                "room_id": room["id"],
                "room": room,
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
