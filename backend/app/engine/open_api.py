"""对外聊天：人设 + 每通道实例一个隐藏工作角色 + 同步回合。"""

from __future__ import annotations

import uuid

from app.engine.channel_plugins.errors import ChannelError
from app.engine.channel_plugins.store import ChannelInstanceStore
from app.engine.channel_plugins.turn_service import ChannelTurnService
from app.engine.channel_plugins.types import SCRIPT_API_TYPE_ID, STATUS_DISABLED, STATUS_ENABLED
from app.engine.roles import API_ROLE_PREFIX, EXT_ROLE_PREFIX, VISIBILITY_HIDDEN, is_api_role_id

OpenApiError = ChannelError


class OpenApiService:
    def __init__(
        self,
        *,
        roles,
        api_keys,
        conversations,
        chat_runner,
        channel_instances: ChannelInstanceStore | None = None,
        channel_turns: ChannelTurnService | None = None,
        channel_registry=None,
        channel_runtime=None,
        settings=None,
        usage=None,
        runtime_store=None,
    ):
        self.roles = roles
        self.api_keys = api_keys
        self.conversations = conversations
        self.chat_runner = chat_runner
        self.channel_instances = channel_instances or ChannelInstanceStore(
            api_keys._path.parent.parent,
            api_keys=api_keys,
        )
        self.channel_turns = channel_turns or ChannelTurnService(
            roles=roles,
            conversations=conversations,
            chat_runner=chat_runner,
        )
        self.channel_registry = channel_registry
        self.channel_runtime = channel_runtime
        self.settings = settings
        self.usage = usage
        self.runtime_store = runtime_store

    def list_types(self) -> list[dict]:
        if self.channel_registry is not None:
            return self.channel_registry.list_types()
        from app.engine.channel_plugins.registry import ChannelPluginRegistry

        return ChannelPluginRegistry.builtin().list_types()

    def list_personas(self) -> list[dict]:
        return self.roles.list_personas()

    def create_persona(
        self,
        *,
        name: str,
        system_prompt: str = "",
        avatar: str | None = None,
    ) -> dict:
        return self.roles.create_persona(
            name=name, system_prompt=system_prompt, avatar=avatar
        )

    def create_persona_from_role(self, role_id: str) -> dict:
        role = self.roles.get(role_id)
        if role.get("visibility") == VISIBILITY_HIDDEN or is_api_role_id(role_id):
            raise OpenApiError("不能从通道工作角色复制人设")
        return self.roles.create_persona(
            name=role.get("name") or "人设",
            system_prompt=role.get("system_prompt") or "",
            avatar=role.get("avatar"),
        )

    def update_persona(self, persona_id: str, **fields) -> dict:
        return self.roles.update_persona(persona_id, **fields)

    def delete_persona(self, persona_id: str) -> None:
        using = self.channel_instances.ids_for_persona(persona_id)
        if using:
            raise OpenApiError("仍有通道在使用此人设，请先停用该通道")
        self.roles.delete_persona(persona_id)

    def list_keys(self) -> list[dict]:
        out = []
        for inst in self.channel_instances.list_all(type_id=SCRIPT_API_TYPE_ID):
            out.append(self._enrich_key(self.channel_instances.as_key(inst)))
        return out

    def list_instances(self) -> list[dict]:
        return [
            self._enrich_instance(item) for item in self.channel_instances.list_all()
        ]

    def _enrich_key(self, key: dict) -> dict:
        item = dict(key)
        item["persona"] = self._persona_or_none(key.get("persona_id"))
        return item

    def _enrich_instance(self, inst: dict) -> dict:
        item = dict(inst)
        item["persona"] = self._persona_or_none(inst.get("persona_id"))
        if item.get("type_id") == "feishu":
            cfg = dict(item.get("config") or {})
            if str(cfg.get("ingress") or "websocket") == "http_webhook":
                cfg["webhook_url"] = self._callback_url(item.get("id"), "feishu")
            item["config"] = cfg
        elif item.get("type_id") == "slack":
            cfg = dict(item.get("config") or {})
            if str(cfg.get("ingress") or "websocket") == "http_webhook":
                cfg["request_url"] = self._callback_url(item.get("id"), "slack")
            item["config"] = cfg
        elif item.get("type_id") == "wecom":
            cfg = dict(item.get("config") or {})
            cfg["callback_url"] = self._callback_url(item.get("id"), "wecom")
            item["config"] = cfg
        elif item.get("type_id") == "dingtalk":
            cfg = dict(item.get("config") or {})
            if str(cfg.get("ingress") or "websocket") == "http_webhook":
                cfg["webhook_url"] = self._callback_url(item.get("id"), "dingtalk")
            item["config"] = cfg
        return item

    def _callback_url(self, instance_id: str | None, type_id: str) -> str:
        base = (self._public_base_url() or "").rstrip("/")
        if not base or not instance_id:
            return ""
        return f"{base}/api/channels/{instance_id}/{type_id}"

    def _persona_or_none(self, persona_id: str | None) -> dict | None:
        if not persona_id:
            return None
        try:
            return self.roles.get_persona(persona_id)
        except KeyError:
            return None

    def create_key(
        self,
        *,
        name: str,
        persona_id: str | None = None,
        persona_name: str | None = None,
        persona_prompt: str = "",
        persona_avatar: str | None = None,
    ) -> dict:
        created = self.create_instance(
            type_id=SCRIPT_API_TYPE_ID,
            name=name,
            persona_id=persona_id,
            persona_name=persona_name,
            persona_prompt=persona_prompt,
            persona_avatar=persona_avatar,
        )
        key = self._enrich_key(self.channel_instances.as_key(created))
        if created.get("token"):
            key["token"] = created["token"]
        return key

    def create_instance(
        self,
        *,
        type_id: str,
        name: str,
        persona_id: str | None = None,
        persona_name: str | None = None,
        persona_prompt: str = "",
        persona_avatar: str | None = None,
        config: dict | None = None,
        secrets: dict | None = None,
        enabled: bool = True,
    ) -> dict:
        adapter = None
        if self.channel_registry is not None:
            if not self.channel_registry.has_adapter(type_id):
                raise OpenApiError("该通道类型即将支持")
            adapter = self.channel_registry.get(type_id)
        elif type_id != SCRIPT_API_TYPE_ID:
            raise OpenApiError("该通道类型即将支持")
        if persona_id:
            persona = self.roles.get_persona(persona_id)
        else:
            pname = (persona_name or name or "").strip() or "聊天通道"
            persona = self.roles.create_persona(
                name=pname,
                system_prompt=persona_prompt or "",
                avatar=persona_avatar,
            )
        key_id = uuid.uuid4().hex[:12]
        prefix = API_ROLE_PREFIX if type_id == SCRIPT_API_TYPE_ID else EXT_ROLE_PREFIX
        role_id = f"{prefix}{key_id}"
        display = f"{persona['name']} · {name.strip()}"
        self.roles.create(
            name=display[:80],
            system_prompt="",
            avatar=persona.get("avatar"),
            role_id=role_id,
            visibility=VISIBILITY_HIDDEN,
            persona_id=persona["id"],
            onboarding_status="completed",
        )
        if type_id == SCRIPT_API_TYPE_ID:
            raw, record = self.channel_instances.create_script(
                name=name,
                persona_id=persona["id"],
                role_id=role_id,
                instance_id=key_id,
            )
            return {**self._enrich_instance(record), "token": raw}

        cfg = dict(config or {})
        for key in ("webhook_url", "request_url", "callback_url"):
            cfg.pop(key, None)
        sec = dict(secrets or {})
        status, detail = (STATUS_ENABLED, None)
        if adapter is not None:
            status, detail = adapter.validate_config(
                cfg,
                sec,
                public_base_url=self._public_base_url(),
                enabling=bool(enabled),
            )
        if not enabled:
            status, detail = STATUS_DISABLED, None
        record = self.channel_instances.create(
            type_id=type_id,
            name=name,
            persona_id=persona["id"],
            role_id=role_id,
            config=cfg,
            secrets=sec,
            enabled=bool(enabled),
            status=status,
            status_detail=detail,
            instance_id=key_id,
        )
        if enabled and status == STATUS_ENABLED and self.channel_runtime is not None:
            self.channel_runtime.sync_instance(record["id"])
        return self._enrich_instance(record)

    def _public_base_url(self) -> str | None:
        if self.settings is None:
            return None
        return (getattr(self.settings, "public_base_url", None) or "").strip() or None

    def revoke_key(self, key_id: str) -> dict:
        return self._enrich_key(
            self.channel_instances.as_key(self.channel_instances.set_enabled(key_id, False))
        )

    def revoke_instance(self, instance_id: str) -> dict:
        updated = self._enrich_instance(
            self.channel_instances.set_enabled(instance_id, False)
        )
        if self.channel_runtime is not None:
            self.channel_runtime.sync_instance(instance_id)
        return updated

    def update_instance(
        self,
        instance_id: str,
        *,
        name: str | None = None,
        persona_id: str | None = None,
        enabled: bool | None = None,
        config: dict | None = None,
        secrets: dict | None = None,
    ) -> dict:
        if persona_id:
            self.roles.get_persona(persona_id)
        if config is not None:
            config = {
                k: v
                for k, v in config.items()
                if k not in {"webhook_url", "request_url", "callback_url"}
            }
        internal = self.channel_instances.get_internal(instance_id)
        type_id = internal.get("type_id") or SCRIPT_API_TYPE_ID
        adapter = None
        if self.channel_registry is not None and self.channel_registry.has_adapter(type_id):
            adapter = self.channel_registry.get(type_id)
        merged_config = dict(internal.get("config") or {})
        if config:
            merged_config.update({k: v for k, v in config.items() if v is not None})
        for key in ("webhook_url", "request_url", "callback_url"):
            merged_config.pop(key, None)
        from app.engine.channel_plugins.secret_mask import merge_secrets

        merged_secrets = merge_secrets(internal.get("secrets") or {}, secrets)
        enabling = internal.get("enabled") if enabled is None else bool(enabled)
        status = None
        detail = None
        if adapter is not None:
            status, detail = adapter.validate_config(
                merged_config,
                merged_secrets,
                public_base_url=self._public_base_url(),
                enabling=bool(enabling),
            )
            if not enabling:
                status, detail = STATUS_DISABLED, None
        updated = self.channel_instances.update(
            instance_id,
            name=name,
            persona_id=persona_id,
            enabled=enabled,
            status=status,
            status_detail=detail,
            config=config,
            secrets=secrets,
        )
        if persona_id and updated.get("role_id"):
            try:
                self.roles.set_persona_id(updated["role_id"], persona_id)
            except KeyError:
                pass
        if self.channel_runtime is not None:
            self.channel_runtime.sync_instance(instance_id)
        return self._enrich_instance(updated)

    def instance_credential(self, instance_id: str) -> dict:
        """主人 Cookie 会话取出可复制凭证。列表接口不带明文。"""
        internal = self.channel_instances.get_internal(instance_id)
        public = self._enrich_instance(self.channel_instances.get(instance_id))
        type_id = str(internal.get("type_id") or SCRIPT_API_TYPE_ID)
        secrets = dict(internal.get("secrets") or {})
        config = dict(public.get("config") or {})
        if type_id == SCRIPT_API_TYPE_ID:
            token = str(secrets.get("key_plaintext") or "").strip()
            prefix = str(config.get("key_prefix") or "").strip()
            display = token[:18] + "…" if len(token) > 18 else (token or prefix)
            return {
                "kind": "token",
                "token": token or None,
                "prefix": prefix,
                "display": display or "KEY",
                "copy_text": token,
                "can_copy_full": bool(token),
            }
        copy_parts: list[str] = []
        for key in (
            "app_id",
            "corp_id",
            "agent_id",
            "app_key",
            "robot_code",
            "webhook_url",
            "request_url",
            "callback_url",
        ):
            value = str(config.get(key) or "").strip()
            if value:
                copy_parts.append(f"{key}: {value}")
        for key, raw in secrets.items():
            if key in {"key_hash", "key_plaintext"}:
                continue
            value = str(raw or "").strip()
            if value:
                copy_parts.append(f"{key}: {value}")
        copy_text = "\n".join(copy_parts)
        return {
            "kind": "secrets",
            "token": None,
            "prefix": "",
            "display": "凭证已保存",
            "copy_text": copy_text,
            "can_copy_full": bool(copy_text),
        }

    def instance_logs(self, instance_id: str, *, limit: int = 50, offset: int = 0) -> dict:
        self.channel_instances.get(instance_id)
        if self.runtime_store is None:
            return {"items": [], "limit": limit, "offset": offset}
        items = self.runtime_store.list_logs(instance_id, limit=limit, offset=offset)
        return {"items": items, "limit": limit, "offset": offset}

    def instance_usage(
        self,
        instance_id: str,
        *,
        granularity: str = "day",
        start: str | None = None,
        end: str | None = None,
    ) -> dict:
        self.channel_instances.get(instance_id)
        if self.usage is None:
            return {"totals": {}, "by_bucket": [], "by_model": []}
        return self.usage.summary(
            granularity=granularity,
            start=start,
            end=end,
            channel_instance_id=instance_id,
        )

    def resolve_bearer(self, raw: str) -> dict | None:
        rec = self.channel_instances.resolve_script_token(raw)
        if rec is None:
            return None
        self.channel_instances.touch(rec["id"])
        return rec

    def _assert_key_conversation(self, key: dict, cid: str) -> dict:
        return self.channel_turns.assert_instance_conversation(key, cid)

    async def complete_chat(
        self,
        *,
        key: dict,
        message: str,
        conversation_id: str | None = None,
        skills: list[str] | None = None,
        title: str | None = None,
        timeout_sec: float = 120,
    ) -> dict:
        return await self.channel_turns.complete_chat(
            record=key,
            message=message,
            conversation_id=conversation_id,
            skills=skills,
            title=title,
            timeout_sec=timeout_sec,
            type_id=SCRIPT_API_TYPE_ID,
        )

    def list_key_conversations(self, key_id: str) -> list[dict]:
        try:
            inst = self.channel_instances.get(key_id)
        except KeyError as e:
            raise OpenApiError("通道不存在", code="not_found", status=404) from e
        role_id = inst.get("role_id")
        if not role_id:
            return []
        return self.conversations.list_all(role_id=role_id)
