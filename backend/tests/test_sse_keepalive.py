"""SSE keepalive 单元测试。"""

import asyncio

import pytest

from app.engine.chat.sse_keepalive import with_sse_keepalive


@pytest.mark.asyncio
async def test_keepalive_inserts_comment_during_silence():
    async def slow():
        yield "data: a\n\n"
        await asyncio.sleep(0.08)
        yield "data: b\n\n"

    out = []
    async for chunk in with_sse_keepalive(slow(), interval_sec=0.03):
        out.append(chunk)

    assert out[0] == "data: a\n\n"
    assert ": keepalive\n\n" in out
    assert out[-1] == "data: b\n\n"


@pytest.mark.asyncio
async def test_keepalive_preserves_contextvar_across_yields():
    """上游生成器内的 ContextVar token 必须能在同一 Context 里 reset。"""
    from contextvars import ContextVar

    var: ContextVar[str | None] = ContextVar("keepalive_test_var", default=None)

    async def gen():
        token = var.set("bound")
        try:
            yield "data: 1\n\n"
            await asyncio.sleep(0.05)
            yield "data: 2\n\n"
        finally:
            var.reset(token)  # 若跨 Task 恢复生成器，这里会炸

    out = []
    async for chunk in with_sse_keepalive(gen(), interval_sec=0.02):
        out.append(chunk)
    assert "data: 1\n\n" in out
    assert "data: 2\n\n" in out
    assert var.get() is None
