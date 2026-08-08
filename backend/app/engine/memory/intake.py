"""已废除：按条消息 MemoryIntake。

生产路径请用 SessionMemoryObserve（session_observe_memory）或 MemoryService.resolver。
"""

from __future__ import annotations


class MemoryIntake:
    """遗留入口：构造即失败，勿在新代码中调用。"""

    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "MemoryIntake 已废除：请使用 SessionMemoryObserve 或 MemoryService.resolver"
        )


__all__ = ["MemoryIntake"]
