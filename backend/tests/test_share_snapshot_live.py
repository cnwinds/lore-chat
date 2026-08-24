"""分享快照 live 会话单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.engine.share_snapshot import (
    conversation_share_public_title,
    is_live_conversation_share,
    load_conversation_for_share,
    materialize_conversation_snapshot,
)
from app.models.share_links import ShareLink


def _link(**kwargs) -> ShareLink:
    defaults = dict(
        share_id="abcdefghijklmnopqr",
        type="conversation",
        title="创建时标题",
        created_at="2026-08-24T10:00:00+00:00",
        exp=None,
        revoked=False,
        view_count=0,
        payload_ref=".kb/shares/x.json",
        options={"pin_version": True},
    )
    defaults.update(kwargs)
    return ShareLink(**defaults)


def test_is_live_conversation_share():
    assert not is_live_conversation_share(_link())
    assert is_live_conversation_share(
        _link(payload_ref="conv:abc", options={"pin_version": False, "conversation_id": "abc"})
    )
    assert not is_live_conversation_share(
        _link(payload_ref="conv:abc", options={"pin_version": True, "conversation_id": "abc"})
    )
    assert is_live_conversation_share(
        _link(payload_ref="conv:abc", options={"conversation_id": "abc"})
    )


def test_conversation_share_public_title_live_uses_snapshot_title():
    link = _link(
        title="创建时标题",
        payload_ref="conv:c1",
        options={"pin_version": False, "conversation_id": "c1"},
    )
    assert (
        conversation_share_public_title(link, {"title": "当前会话名"})
        == "当前会话名"
    )
    assert conversation_share_public_title(_link(), {"title": "x"}) == "创建时标题"


class _FakeConversations:
    def __init__(self, data: dict[str, dict]) -> None:
        self._data = data

    def get(self, cid: str) -> dict:
        if cid not in self._data:
            raise KeyError(cid)
        return self._data[cid]


def test_load_conversation_for_share_live(tmp_path):
    link = _link(
        payload_ref="conv:c1",
        options={"pin_version": False, "conversation_id": "c1"},
    )
    conv = {
        "title": "live",
        "messages": [
            {"id": "m1", "role": "user", "text": "hi", "ts": "t", "status": "complete"},
        ],
    }
    snap = load_conversation_for_share(
        link,
        kb_path=tmp_path,
        conversations=_FakeConversations({"c1": conv}),
    )
    assert snap["title"] == "live"
    assert len(snap["messages"]) == 1


def test_materialize_preserves_message_order_with_reordered_ids():
    conv = {
        "messages": [
            {"id": "a", "role": "user", "text": "1", "ts": "t", "status": "complete"},
            {"id": "b", "role": "assistant", "text": "2", "ts": "t", "status": "complete"},
            {"id": "c", "role": "user", "text": "3", "ts": "t", "status": "complete"},
        ]
    }
    snap = materialize_conversation_snapshot(conv, message_ids=["c", "a"])
    assert [m["id"] for m in snap["messages"]] == ["a", "c"]
