"""角色相关 Agent 工具。"""

from __future__ import annotations


class RoleTools:
    def __init__(self, roles) -> None:
        self.roles = roles

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
