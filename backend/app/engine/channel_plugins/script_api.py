"""第一种聊天通道：脚本 / HTTP Bearer。回合走 ChannelTurnService，不在此编排。"""

from __future__ import annotations

from typing import Any

from app.engine.channel_plugins.types import (
    STATUS_ENABLED,
    STATUS_ERROR,
    ChannelTypeSpec,
    InboundEvent,
    SCRIPT_API_TYPE_ID,
)


class ScriptApiAdapter:
    spec = ChannelTypeSpec(
        type_id=SCRIPT_API_TYPE_ID,
        display_name="脚本 / HTTP",
        ingress="http_bearer",
        needs_public_url=False,
        available=True,
        ack_deadline_ms=None,
        capabilities=frozenset({"sync_reply"}),
        config_schema={
            "type": "object",
            "properties": {"key_prefix": {"type": "string"}},
        },
        secret_schema={
            "type": "object",
            "properties": {"key_hash": {"type": "string"}},
        },
    )

    def validate_config(
        self,
        config: dict[str, Any],
        secrets: dict[str, Any],
        *,
        public_base_url: str | None = None,
        enabling: bool = False,
    ) -> tuple[str, str | None]:
        del config, public_base_url, enabling
        if (secrets or {}).get("key_hash"):
            return STATUS_ENABLED, None
        return STATUS_ERROR, "未签发密钥"

    def start(self, instance: dict[str, Any]) -> None:
        del instance

    def stop(self, instance: dict[str, Any]) -> None:
        del instance

    def parse_inbound(self, raw: Any) -> InboundEvent:
        del raw
        raise NotImplementedError("script_api 走 POST /api/v1/chat")

    def send_outbound(
        self,
        instance: dict[str, Any],
        text: str,
        **kwargs: Any,
    ) -> None:
        del instance, text, kwargs
        raise NotImplementedError("script_api 同步 JSON 回复")

    def challenge(self, raw: Any) -> Any | None:
        del raw
        return None
