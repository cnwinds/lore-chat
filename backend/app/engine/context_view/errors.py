from __future__ import annotations


class ContextViewError(Exception):
    """统一上下文视图解析/范围错误基类。"""


class InvalidUri(ContextViewError):
    """URI 语法、别名或段数不合法。"""

    def __init__(self, message: str, *, uri: str | None = None) -> None:
        self.uri = uri
        super().__init__(message)


class OutOfScope(ContextViewError):
    """路径不在本回合可见根之内。"""

    def __init__(self, uri_str: str) -> None:
        self.uri_str = uri_str
        super().__init__(f"路径越界: {uri_str}")


class NotFound(ContextViewError):
    """可见结构内找不到对应资源（如会话与桶/归属不匹配）。"""

    def __init__(self, message: str, *, uri: str | None = None) -> None:
        self.uri = uri
        super().__init__(message)


class AmbiguousSubject(InvalidUri):
    """可见范围内名字不唯一。"""
