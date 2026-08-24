"""媒体授权（capability URL）测试。"""

from __future__ import annotations

import time
from pathlib import Path

from app.models.media_grants import (
    DEFAULT_MEDIA_GRANT_TTL_SEC,
    MediaGrantStore,
    build_media_grant_url,
)


def test_issue_and_resolve_grant(tmp_path: Path):
    store = MediaGrantStore(tmp_path)
    t0 = 1_000_000.0
    gid = store.issue("媒体/a.mp4", ttl_sec=300, now=t0)
    g = store.resolve(gid, now=t0 + 10)
    assert g is not None
    assert g.rel_path == "媒体/a.mp4"


def test_grant_expires(tmp_path: Path):
    store = MediaGrantStore(tmp_path)
    t0 = 1_000_000.0
    gid = store.issue("媒体/a.mp4", ttl_sec=60, now=t0)
    assert store.resolve(gid, now=t0 + 30) is not None
    assert store.resolve(gid, now=t0 + 61) is None


def test_build_media_grant_url_shape(tmp_path: Path):
    url = build_media_grant_url(
        public_base_url="https://app.example.com",
        rel_path="媒体/demo.mp4",
        kb_path=tmp_path,
    )
    assert url.startswith("https://app.example.com/api/media/grant/")
    assert "媒体" not in url
    assert "token=" not in url


def test_prune_on_issue(tmp_path: Path):
    store = MediaGrantStore(tmp_path)
    t0 = 2_000_000.0
    old = store.issue("媒体/old.mp4", ttl_sec=60, now=t0)
    assert store.resolve(old, now=t0 + 61) is None
    new = store.issue("媒体/new.mp4", ttl_sec=DEFAULT_MEDIA_GRANT_TTL_SEC, now=t0 + 100)
    assert store.resolve(new, now=t0 + 200) is not None
