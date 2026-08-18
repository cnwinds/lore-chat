"""按请求绑定的演示访客上下文（ContextVar）。

DEMO_MODE 是部署开关；本模块表示「当前请求是访客」。
管理员在同一 demo 部署上不受只读 / 工具裁剪限制。
"""

from __future__ import annotations

from contextvars import ContextVar, Token

_demo_guest: ContextVar[bool] = ContextVar("demo_guest", default=False)


def is_demo_guest() -> bool:
    return _demo_guest.get()


def bind_demo_guest(value: bool) -> Token:
    return _demo_guest.set(value)


def reset_demo_guest(token: Token) -> None:
    _demo_guest.reset(token)
