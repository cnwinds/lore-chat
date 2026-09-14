"""进程内通道类型注册。用户不能从网店安装。"""

from __future__ import annotations

from app.engine.channel_plugins.adapter import ChannelAdapter
from app.engine.channel_plugins.dingtalk import DingtalkAdapter
from app.engine.channel_plugins.errors import ChannelError
from app.engine.channel_plugins.feishu import FeishuAdapter
from app.engine.channel_plugins.script_api import ScriptApiAdapter
from app.engine.channel_plugins.slack import SlackAdapter
from app.engine.channel_plugins.types import ChannelTypeSpec, SCRIPT_API_TYPE_ID
from app.engine.channel_plugins.wecom import WecomAdapter

# 仅元数据，供设置向导灰显「即将支持」。已落地的类型走 adapter。
_UPCOMING_SPECS = (
    ChannelTypeSpec(
        type_id="wechat_mp",
        display_name="微信公众号",
        ingress="http_webhook",
        needs_public_url=True,
        available=False,
        capabilities=frozenset({"async_reply"}),
    ),
)


class ChannelPluginRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, ChannelAdapter] = {}
        self._upcoming: list[ChannelTypeSpec] = []

    def register(self, adapter: ChannelAdapter) -> None:
        self._adapters[adapter.spec.type_id] = adapter

    def add_upcoming(self, spec: ChannelTypeSpec) -> None:
        self._upcoming.append(spec)

    def get(self, type_id: str) -> ChannelAdapter:
        adapter = self._adapters.get(type_id)
        if adapter is None:
            if any(item.type_id == type_id for item in self._upcoming):
                raise ChannelError("该通道类型即将支持")
            raise ChannelError("未知通道类型")
        return adapter

    def has_adapter(self, type_id: str) -> bool:
        return type_id in self._adapters

    def list_types(self) -> list[dict]:
        seen: set[str] = set()
        out: list[dict] = []
        for adapter in self._adapters.values():
            seen.add(adapter.spec.type_id)
            out.append(adapter.spec.public())
        for spec in self._upcoming:
            if spec.type_id in seen:
                continue
            out.append(spec.public())
        return out

    @classmethod
    def builtin(cls) -> ChannelPluginRegistry:
        registry = cls()
        registry.register(ScriptApiAdapter())
        registry.register(FeishuAdapter())
        registry.register(SlackAdapter())
        registry.register(WecomAdapter())
        registry.register(DingtalkAdapter())
        for spec in _UPCOMING_SPECS:
            registry.add_upcoming(spec)
        return registry


def default_script_type_id() -> str:
    return SCRIPT_API_TYPE_ID
