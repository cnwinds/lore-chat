"""聊天通道公共模型：origin、类型元数据、入站事件。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 脚本保持字符串 "api"；其它类型用 type_id。左栏 / 记忆调度排除整个集合。
CHANNEL_ORIGINS = frozenset(
    {"api", "feishu", "slack", "wecom", "dingtalk", "wechat_mp"}
)
WEB_ORIGIN = "web"

SCRIPT_API_TYPE_ID = "script_api"
EXT_ROLE_PREFIX = "ext_"

STATUS_DISABLED = "disabled"
STATUS_ENABLED = "enabled"
STATUS_ERROR = "error"


def is_channel_origin(origin: str | None) -> bool:
    value = (origin or WEB_ORIGIN).strip() or WEB_ORIGIN
    return value in CHANNEL_ORIGINS


def is_allowed_conversation_origin(origin: str | None) -> bool:
    value = (origin or WEB_ORIGIN).strip() or WEB_ORIGIN
    return value == WEB_ORIGIN or value in CHANNEL_ORIGINS


def origin_for_type(type_id: str) -> str:
    if type_id == SCRIPT_API_TYPE_ID:
        return "api"
    return (type_id or "").strip() or "api"


def sql_exclude_channel_origins(column: str = "c.origin") -> str:
    listed = ", ".join(f"'{item}'" for item in sorted(CHANNEL_ORIGINS))
    return f"COALESCE({column}, 'web') NOT IN ({listed})"


@dataclass(frozen=True)
class ChannelTypeSpec:
    type_id: str
    display_name: str
    ingress: str
    needs_public_url: bool
    available: bool
    ack_deadline_ms: int | None = None
    capabilities: frozenset[str] = field(default_factory=frozenset)
    config_schema: dict[str, Any] = field(default_factory=dict)
    secret_schema: dict[str, Any] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        return {
            "type_id": self.type_id,
            "display_name": self.display_name,
            "ingress": self.ingress,
            "needs_public_url": self.needs_public_url,
            "available": self.available,
            "ack_deadline_ms": self.ack_deadline_ms,
            "capabilities": sorted(self.capabilities),
            "config_schema": self.config_schema,
            "secret_schema": self.secret_schema,
        }


@dataclass
class InboundMedia:
    """待物化为知识库 attachments 路径的入站文件。"""

    filename: str
    kind: str = "image"
    mime: str | None = None
    data: bytes | None = None
    url: str | None = None
    file_key: str | None = None


@dataclass
class InboundEvent:
    instance_id: str
    text: str
    event_id: str | None = None
    external_user_id: str | None = None
    display_name: str | None = None
    external_chat_id: str | None = None
    external_thread_id: str | None = None
    reply_to_id: str | None = None
    attachments: list[str] = field(default_factory=list)
    media: list[InboundMedia] = field(default_factory=list)
    is_group: bool = False
    mentioned_bot: bool = False
    quoted: bool = False
    extra: dict[str, Any] = field(default_factory=dict)
