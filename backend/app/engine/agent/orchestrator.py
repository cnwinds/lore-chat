from __future__ import annotations

import time
from collections.abc import AsyncIterator

from app.config import Settings
from app.engine.agent.message_builder import build_agent_messages
from app.engine.agent.prompts import MODE_DEFAULT
from app.engine.agent.skill_activation import build_skill_catalog_system_messages
from app.engine.agent.tool_loop import AgentToolLoop
from app.engine.agent.tools import ToolRegistry, select_tools


class AgentOrchestrator:
    """Agent 运行入口：组装消息与模式，委托 AgentToolLoop 执行 LLM+工具循环。"""

    def __init__(
        self,
        settings: Settings,
        llm,
        tools: ToolRegistry,
        system_layer=None,
    ):
        self._settings = settings
        self._llm = llm
        self.tools = tools
        self.system_layer = system_layer
        self._tool_loop = AgentToolLoop(settings, llm, tools)

    @property
    def settings(self) -> Settings:
        return self._settings

    @settings.setter
    def settings(self, value: Settings) -> None:
        self._settings = value
        self._tool_loop.settings = value

    @property
    def llm(self):
        return self._llm

    @llm.setter
    def llm(self, value) -> None:
        self._llm = value
        self._tool_loop.llm = value

    async def run(
        self,
        user_text: str,
        *,
        mode: str = MODE_DEFAULT,
        active_doc_path: str | None = None,
        active_doc_paths: list[str] | None = None,
        primary_doc_path: str | None = None,
        skill_catalog: list[dict[str, str]] | None = None,
        history: list[dict] | None = None,
        conversation_id: str | None = None,
        turn_id: str | None = None,
        run_id: str | None = None,
        web_enabled: bool = False,
        inject_broker=None,
        on_inject_applied=None,
        attachments: list[str] | None = None,
    ) -> AsyncIterator[str]:
        system_layer_text = (
            self.system_layer.compose_rules() if self.system_layer else ""
        )
        user_memory = (
            self.system_layer.memory_context() if self.system_layer else ""
        )
        catalog = list(skill_catalog) if skill_catalog else []
        skill_msgs = build_skill_catalog_system_messages(catalog)
        search_configured = (
            self.tools.web_search is not None
            and self.tools.web_search.provider is not None
        )
        imagegen_configured = bool(
            self.tools.image_tools.image_gen is not None
            and self.tools.image_tools.image_gen.configured
        )
        web_search_enabled = web_enabled and search_configured
        messages = build_agent_messages(
            user_text,
            mode=mode,
            web_enabled=web_search_enabled,
            system_layer_text=system_layer_text,
            user_memory=user_memory,
            history=history,
            active_doc_path=active_doc_path,
            active_doc_paths=active_doc_paths,
            primary_doc_path=primary_doc_path,
            extra_system_messages=skill_msgs or None,
            attachments=attachments,
        )
        tools_for_run = select_tools(
            mode,
            web_enabled,
            search_configured=search_configured,
            imagegen_configured=imagegen_configured,
            sandbox_enabled=bool(
                self.settings.sandbox_enabled and self.tools.sandbox_runtime is not None
            ),
            disclosure_windows=self.tools.disclosure_windows,
        )
        primary = primary_doc_path or active_doc_path
        start = time.monotonic()
        async for ev in self._tool_loop.stream(
            messages,
            tools_for_run=tools_for_run,
            conversation_id=conversation_id,
            active_doc_path=primary,
            started_at=start,
            turn_id=turn_id,
            run_id=run_id,
            inject_broker=inject_broker,
            on_inject_applied=on_inject_applied,
        ):
            yield ev
