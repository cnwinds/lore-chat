from __future__ import annotations

from app.engine.agent.tool_catalog import (
    TOOL_DEFINITIONS,
    TOOL_LABELS,
    WRITE_TOOLS,
    READ_ONLY_TOOLS,
    _DEFAULT_DISCLOSURE_CHARS,
    can_parallelize,
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
from app.engine.knowledge_writer import KnowledgeWriter

__all__ = [
    "ToolRegistry",
    "TOOL_DEFINITIONS",
    "TOOL_LABELS",
    "select_tools",
    "can_parallelize",
    "READ_ONLY_TOOLS",
    "WRITE_TOOLS",
]


class ToolRegistry:
    """Agent 工具 adapter：组装各执行 module，经 dispatch 对外暴露 execute。"""

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
        disclosure_chars: int = _DEFAULT_DISCLOSURE_CHARS,
        edit_doc_max_edits: int = 10,
        edit_doc_max_patch_chars: int = 8192,
        edit_doc_require_read: bool = True,
        conversation_context_max_chars: int = 12000,
        memory_service=None,
    ):
        del indexer  # 保留构造签名，索引经 knowledge_writer
        self.repo = repo
        self.organizer = organizer
        self.pending = pending
        self.conversations = conversations
        self.system_layer = system_layer
        self.knowledge_writer = knowledge_writer
        self.disclosure_chars = disclosure_chars
        self.edit_doc_require_read = edit_doc_require_read

        read_guard = DocReadGuard(require_read=edit_doc_require_read)
        self.kb_read = KbReadTools(
            repo=repo,
            retriever=retriever,
            read_guard=read_guard,
            disclosure_chars=disclosure_chars,
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
            disclosure_chars=disclosure_chars,
        )
        self.memory = MemoryTools(memory_service)
        self.interaction = InteractionTools(pending)
        self._dispatch_handlers = None

    @property
    def fetcher(self):
        return self.web.fetcher

    @fetcher.setter
    def fetcher(self, value) -> None:
        self.web.fetcher = value

    @property
    def web_search(self):
        return self.web.web_search

    @web_search.setter
    def web_search(self, value) -> None:
        self.web.web_search = value

    @property
    def memory_service(self):
        return self.memory.memory_service

    @memory_service.setter
    def memory_service(self, value) -> None:
        self.memory.memory_service = value

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

    def _search_kb(self, args: dict, *, conversation_id: str | None = None) -> dict:
        return self.kb_read.search_kb(args, conversation_id=conversation_id)

    def _read_doc(self, args: dict, *, conversation_id: str | None = None) -> dict:
        return self.kb_read.read_doc(args, conversation_id=conversation_id)

    def _list_kb_structure(self, args: dict) -> dict:
        return self.kb_read.list_kb_structure(args)

    def _read_conversation_context(self, args: dict) -> dict:
        return self.kb_read.read_conversation_context(args)

    async def _fetch_url(self, args: dict) -> dict:
        return await self.web.fetch_url(args)

    async def _web_search(self, args: dict) -> dict:
        return await self.web.web_search(args)

    def _write_kb(self, args: dict) -> dict:
        return self.kb_mutate.write_kb(args)

    def _summarize_conversation(
        self, args: dict, *, conversation_id: str | None = None
    ) -> dict:
        return self.kb_mutate.summarize_conversation(
            args, conversation_id=conversation_id
        )

    def _move_entry(self, args: dict) -> dict:
        return self.kb_mutate.move_entry(args)

    def _delete_kb(self, args: dict) -> dict:
        return self.kb_mutate.delete_kb(args)

    def _edit_doc(self, args: dict, *, conversation_id: str | None = None) -> dict:
        return self.kb_mutate.edit_doc(args, conversation_id=conversation_id)

    def _manage_memory(self, args: dict, *, conversation_id: str | None = None) -> dict:
        return self.memory.manage_memory(args, conversation_id=conversation_id)

    def _recall_memory(self, args: dict) -> dict:
        return self.memory.recall_memory(args)

    def _ask_user(self, args: dict) -> dict:
        return self.interaction.ask_user(args)
