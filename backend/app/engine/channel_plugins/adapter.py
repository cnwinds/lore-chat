"""通道适配器协议。类型只做厂商/协议；回合不在这里编排。"""

from __future__ import annotations

from typing import Any, Protocol

from app.engine.channel_plugins.types import ChannelTypeSpec, InboundEvent


class ChannelAdapter(Protocol):
    spec: ChannelTypeSpec

    def validate_config(
        self,
        config: dict[str, Any],
        secrets: dict[str, Any],
        *,
        public_base_url: str | None = None,
        enabling: bool = False,
    ) -> tuple[str, str | None]:
        """返回 (status, status_detail)。"""
        ...

    def start(self, instance: dict[str, Any]) -> None: ...

    def stop(self, instance: dict[str, Any]) -> None: ...

    def parse_inbound(self, raw: Any) -> InboundEvent: ...

    def send_outbound(
        self,
        instance: dict[str, Any],
        text: str,
        **kwargs: Any,
    ) -> None: ...

    def challenge(self, raw: Any) -> Any | None: ...
