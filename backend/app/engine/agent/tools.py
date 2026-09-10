from __future__ import annotations

from app.engine.agent.tool_catalog import (
    TOOL_DEFINITIONS,
    TOOL_LABELS,
    WRITE_TOOLS,
    READ_ONLY_TOOLS,
    PARALLELIZABLE_TOOLS,
    can_parallelize,
    resolve_tool_label,
    select_tools,
)
from app.engine.agent.tool_dispatch import dispatch_tool
from app.engine.agent.tool_impl import (
    DocReadGuard,
    InteractionTools,
    KbMutateTools,
    KbReadTools,
    MemoryTools,
    WebReadTools,
)
from app.engine.agent.tool_impl.image_tools import ImageGenTools
from app.engine.agent.tool_impl.role_tools import RoleTools
from app.engine.agent.tool_impl.sandbox_tools import SandboxTools
from app.engine.disclosure import DisclosureWindows
from app.engine.imagegen import ImageGen
from app.engine.knowledge_writer import KnowledgeWriter
from app.engine.sandbox.protocol import SandboxRuntime
from app.engine.sandbox.role_pool import RoleSandboxPool

__all__ = [
    "ToolRegistry",
    "TOOL_DEFINITIONS",
    "TOOL_LABELS",
    "resolve_tool_label",
    "select_tools",
    "can_parallelize",
    "READ_ONLY_TOOLS",
    "WRITE_TOOLS",
    "PARALLELIZABLE_TOOLS",
]


class ToolRegistry:
    """Agent 工具 deep module：组装 tool_impl，对外仅 execute / rebind / interrupt。"""

    def __init__(
        self,
        retriever,
        repo,
        organizer,
        fetcher,
        web_search,
        pending,
        knowledge_writer: KnowledgeWriter,
        conversations=None,
        system_layer=None,
        indexer=None,
        disclosure_windows: DisclosureWindows | None = None,
        edit_doc_max_edits: int = 10,
        edit_doc_max_patch_chars: int = 8192,
        edit_doc_require_read: bool = True,
        conversation_context_max_chars: int = 12000,
        web_search_default_k: int = 5,
        memory_service=None,
        sandbox_runtime: SandboxRuntime | None = None,
        sandbox_pool: RoleSandboxPool | None = None,
        image_gen: ImageGen | None = None,
        roles=None,
    ):
        del indexer  # 保留构造签名，索引经 knowledge_writer
        self.repo = repo
        self.organizer = organizer
        self.pending = pending
        self.conversations = conversations
        self.system_layer = system_layer
        self.knowledge_writer = knowledge_writer
        self.disclosure_windows = disclosure_windows or DisclosureWindows()
        self.edit_doc_require_read = edit_doc_require_read
        self.sandbox_runtime = sandbox_runtime
        self.sandbox_pool = sandbox_pool

        read_guard = DocReadGuard(require_read=edit_doc_require_read)
        self.kb_read = KbReadTools(
            repo=repo,
            retriever=retriever,
            read_guard=read_guard,
            disclosure_windows=self.disclosure_windows,
            conversations=conversations,
            conversation_context_max_chars=conversation_context_max_chars,
        )
        self.kb_mutate = KbMutateTools(
            repo=repo,
            organizer=organizer,
            knowledge_writer=knowledge_writer,
            read_guard=read_guard,
            memory_service=memory_service,
            conversations=conversations,
            system_layer=system_layer,
            edit_doc_max_edits=edit_doc_max_edits,
            edit_doc_max_patch_chars=edit_doc_max_patch_chars,
        )
        self.web = WebReadTools(
            fetcher=fetcher,
            web_search=web_search,
            disclosure_windows=self.disclosure_windows,
            web_search_default_k=web_search_default_k,
        )
        self.memory = MemoryTools(memory_service)
        self.interaction = InteractionTools(pending)
        self.roles_tools = RoleTools(roles, conversations=conversations)
        self.image_tools = ImageGenTools(image_gen)
        self.sandbox = SandboxTools(
            sandbox_runtime,
            knowledge_writer,
            pending=pending,
            trust_mode=True,
            pool=sandbox_pool,
            conversations=conversations,
            roles=roles,
        )
        self._dispatch_handlers = None

    @property
    def disclosure_chars(self) -> int:
        """Skill 首窗等仍按 spot 默认窗对齐。"""
        return self.disclosure_windows.spot

    @property
    def fetcher(self):
        return self.web.fetcher

    @fetcher.setter
    def fetcher(self, value) -> None:
        self.web.fetcher = value
        self._dispatch_handlers = None

    @property
    def web_search(self):
        return self.web.searcher

    @web_search.setter
    def web_search(self, value) -> None:
        self.web.searcher = value
        self._dispatch_handlers = None

    @property
    def memory_service(self):
        return self.memory.memory_service

    @memory_service.setter
    def memory_service(self, value) -> None:
        self.memory.memory_service = value
        self._dispatch_handlers = None

    def rebind(
        self,
        *,
        fetcher=None,
        web_search=None,
        web_search_default_k: int | None = None,
        memory_service=None,
        sandbox_runtime: SandboxRuntime | None = None,
        sandbox_pool: RoleSandboxPool | None = None,
        sandbox_trust_mode: bool | None = None,
        image_gen: ImageGen | None = None,
    ) -> None:
        """热更新依赖；调用方不必摸 tool_impl 字段。"""
        if fetcher is not None:
            self.fetcher = fetcher
        if web_search is not None:
            self.web_search = web_search
        if web_search_default_k is not None:
            from app.engine.agent.tool_impl.web_read import clamp_web_search_k

            self.web.web_search_default_k = clamp_web_search_k(web_search_default_k)
        if memory_service is not None:
            self.memory_service = memory_service
        if image_gen is not None:
            self.image_tools.image_gen = image_gen
        if sandbox_runtime is not None:
            self.sandbox_runtime = sandbox_runtime
            self.sandbox.runtime = sandbox_runtime
        if sandbox_pool is not None:
            self.sandbox_pool = sandbox_pool
            self.sandbox.pool = sandbox_pool
        if sandbox_trust_mode is not None:
            self.sandbox.trust_mode = sandbox_trust_mode
        self._dispatch_handlers = None

    async def interrupt_runtime(
        self,
        *,
        conversation_id: str | None = None,
        role_id: str | None = None,
    ) -> None:
        """只中断该会话 / 角色的沙箱执行，禁止跨角色 interrupt_all。"""
        rid = role_id
        if not rid and conversation_id and self.conversations is not None:
            try:
                rid = self.conversations.get_role_id(conversation_id)
            except KeyError:
                rid = None
        registry = self.sandbox.execution_engine.registry
        recs = []
        if conversation_id:
            recs = registry.find(conversation_id=conversation_id)
        elif rid:
            recs = registry.find(role_id=rid)
        pool = self.sandbox_pool or getattr(self.sandbox, "pool", None)
        if pool is not None:
            for rec in recs:
                await pool.interrupt_execution(
                    rec.execution_id, role_id=rec.role_id or rid
                )
            if rid:
                await pool.interrupt_role(rid)
            return
        rt = self.sandbox_runtime or getattr(self.sandbox, "runtime", None)
        if rt is None:
            return
        if recs:
            for rec in recs:
                await rt.interrupt(rec.execution_id)
            return
        if conversation_id or rid:
            if hasattr(rt, "interrupt_all"):
                await rt.interrupt_all()

    async def execute(
        self,
        name: str,
        args: dict,
        *,
        active_doc_path: str | None = None,
        conversation_id: str | None = None,
    ) -> dict:
        return await dispatch_tool(
            self,
            name,
            args,
            active_doc_path=active_doc_path,
            conversation_id=conversation_id,
        )
