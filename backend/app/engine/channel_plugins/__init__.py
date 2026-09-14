"""聊天通道插件：公共模型 + 适配器 + 共有回合。"""

from app.engine.channel_plugins.errors import ChannelError
from app.engine.channel_plugins.registry import ChannelPluginRegistry
from app.engine.channel_plugins.store import ChannelInstanceStore
from app.engine.channel_plugins.turn_service import ChannelTurnService
from app.engine.channel_plugins.types import (
    CHANNEL_ORIGINS,
    SCRIPT_API_TYPE_ID,
    is_channel_origin,
)

__all__ = [
    "CHANNEL_ORIGINS",
    "SCRIPT_API_TYPE_ID",
    "ChannelError",
    "ChannelInstanceStore",
    "ChannelPluginRegistry",
    "ChannelTurnService",
    "is_channel_origin",
]
