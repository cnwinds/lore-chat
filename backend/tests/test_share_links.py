"""ShareLinkStore 单元测试。"""

from __future__ import annotations

import time

from app.models.share_links import ShareLinkStore, build_share_url


def test_create_permanent_and_list(tmp_path):
    store = ShareLinkStore(tmp_path)
    link = store.create(
        type="conversation",
        title="测试对话",
        payload_ref=".kb/shares/abc.json",
        ttl_sec=None,
        now=1_000_000.0,
        share_id="abcdefghijklmnopqr",
    )
    assert link.share_id == "abcdefghijklmnopqr"
    assert link.exp is None
    items = store.list_all(now=1_000_000.0)
    assert len(items) == 1
    assert items[0].title == "测试对话"


def test_create_with_ttl_expires(tmp_path):
    store = ShareLinkStore(tmp_path)
    t0 = 2_000_000.0
    link = store.create(
        type="doc",
        title="doc",
        payload_ref="技术/a.md",
        ttl_sec=3600,
        now=t0,
        share_id="docshareid12345678",
    )
    assert store.resolve(link.share_id, now=t0 + 100) is not None
    _, status = store.resolve_public(link.share_id, now=t0 + 3601)
    assert status == "expired"
    assert store.resolve(link.share_id, now=t0 + 3601) is None


def test_revoke(tmp_path):
    store = ShareLinkStore(tmp_path)
    link = store.create(
        type="doc",
        title="x",
        payload_ref="a.md",
        ttl_sec=None,
        share_id="revokeshare1234567",
    )
    assert store.revoke(link.share_id)
    assert store.resolve(link.share_id) is None


def test_build_share_url():
    url = build_share_url(
        public_base_url="https://app.example.com/",
        share_id="abc",
    )
    assert url == "https://app.example.com/share/abc"
