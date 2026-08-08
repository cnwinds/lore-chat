"""兼容入口：生产路径为 SessionMemoryObserve。"""

from __future__ import annotations

from app.engine.memory.session_observe import SessionMemoryObserve

# 历史测试与 deps 仍可能 import MemoryWorker
MemoryWorker = SessionMemoryObserve

__all__ = ["MemoryWorker", "SessionMemoryObserve"]
