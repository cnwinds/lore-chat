from __future__ import annotations


class DocReadGuard:
    """edit_doc 前须 read_doc：按会话记录已读路径。"""

    def __init__(self, *, require_read: bool = True) -> None:
        self.require_read = require_read
        self._paths: dict[str, set[str]] = {}

    def mark(self, conversation_id: str | None, path: str) -> None:
        if not conversation_id:
            return
        self._paths.setdefault(conversation_id, set()).add(path)

    def is_read(self, conversation_id: str | None, path: str) -> bool:
        if not self.require_read:
            return True
        if not conversation_id:
            return False
        return path in self._paths.get(conversation_id, set())
