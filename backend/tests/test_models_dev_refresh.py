"""models.dev：内置目录回退 + 旁路拉取不阻塞主路径。"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import httpx
import pytest

from app.models.models_dev import ModelsDevStore

SAMPLE = {
    "openai": {
        "models": {
            "gpt-4o": {
                "name": "GPT-4o",
                "modalities": {"input": ["text", "image"], "output": ["text"]},
                "reasoning": False,
            }
        }
    }
}


def _write_bundled(path: Path, payload: dict | None = None) -> Path:
    path.write_text(json.dumps(payload or SAMPLE), encoding="utf-8")
    return path


def test_loads_bundled_when_cache_missing(tmp_path: Path):
    bundled = _write_bundled(tmp_path / "bundled.json")
    store = ModelsDevStore(
        tmp_path / "missing_cache.json",
        bundled_path=bundled,
        ttl_sec=3600,
    )
    st = store.status()
    assert st["source"] == "bundled"
    assert st["count"] >= 1
    assert store.lookup("gpt-4o") is not None
    assert st["stale"] is True  # 内置无新鲜拉取时间，允许旁路刷新


def test_ensure_fresh_returns_immediately_when_network_hangs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    bundled = _write_bundled(tmp_path / "bundled.json")
    store = ModelsDevStore(
        tmp_path / "cache.json",
        bundled_path=bundled,
        timeout_sec=30.0,
        ttl_sec=1.0,
    )
    entered = threading.Event()
    release = threading.Event()

    class SlowClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url: str):
            entered.set()
            release.wait(timeout=5)
            raise httpx.TimeoutException("hung")

    monkeypatch.setattr("app.models.models_dev.httpx.Client", SlowClient)

    t0 = time.monotonic()
    source = store.ensure_fresh(force=True)
    elapsed = time.monotonic() - t0

    assert elapsed < 0.5, f"ensure_fresh blocked for {elapsed:.2f}s"
    assert source == "bundled"
    assert entered.wait(timeout=1.0), "background fetch never started"
    release.set()
    # 给旁路线程收尾时间
    deadline = time.monotonic() + 2
    while store.status().get("refreshing") and time.monotonic() < deadline:
        time.sleep(0.02)
    assert store.status().get("refreshing") is False


def test_background_refresh_updates_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bundled = _write_bundled(tmp_path / "bundled.json")
    cache = tmp_path / "cache.json"
    store = ModelsDevStore(cache, bundled_path=bundled, timeout_sec=5.0, ttl_sec=1.0)

    remote = {
        "openai": {
            "models": {
                "gpt-4o": {
                    "name": "GPT-4o Remote",
                    "modalities": {"input": ["text"], "output": ["text"]},
                    "reasoning": False,
                },
                "o3": {
                    "name": "o3",
                    "modalities": {"input": ["text"], "output": ["text"]},
                    "reasoning": True,
                    "reasoning_options": [
                        {"type": "effort", "values": ["low", "high"]}
                    ],
                },
            }
        }
    }

    class OkClient:
        def __init__(self, *args, **kwargs):
            self.timeout = kwargs.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url: str):
            class Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    return remote

            return Resp()

    monkeypatch.setattr("app.models.models_dev.httpx.Client", OkClient)
    assert store.schedule_refresh(force=True) is True
    deadline = time.monotonic() + 3
    while store.status()["source"] != "remote" and time.monotonic() < deadline:
        time.sleep(0.02)
    assert store.status()["source"] == "remote"
    assert store.lookup("o3") is not None
    assert cache.is_file()
    # 短超时应传入 Client
    # （OkClient 记录 timeout；再拉一次确认构造参数）
    seen: dict = {}

    class CaptureClient(OkClient):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            seen["timeout"] = kwargs.get("timeout")

    monkeypatch.setattr("app.models.models_dev.httpx.Client", CaptureClient)
    store2 = ModelsDevStore(
        tmp_path / "c2.json",
        bundled_path=bundled,
        timeout_sec=7.5,
        ttl_sec=0.01,
    )
    store2.schedule_refresh(force=True)
    deadline = time.monotonic() + 3
    while "timeout" not in seen and time.monotonic() < deadline:
        time.sleep(0.02)
    assert seen.get("timeout") == 7.5


def test_packaged_bundled_gz_loads(tmp_path: Path):
    from app.models.models_dev import default_bundled_path

    path = default_bundled_path()
    assert path.is_file(), f"missing packaged catalog: {path}"
    store = ModelsDevStore(
        tmp_path / "no-cache.json",
        bundled_path=path,
        ttl_sec=3600,
    )
    st = store.status()
    assert st["source"] == "bundled"
    assert st["count"] > 10


def test_persist_failure_keeps_previous_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    bundled = _write_bundled(tmp_path / "bundled.json")
    store = ModelsDevStore(
        tmp_path / "cache.json",
        bundled_path=bundled,
        timeout_sec=5.0,
        ttl_sec=1.0,
    )
    assert store.status()["source"] == "bundled"

    class OkClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url: str):
            class Resp:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {
                        "openai": {
                            "models": {
                                "o3": {
                                    "name": "o3",
                                    "modalities": {"input": ["text"]},
                                    "reasoning": True,
                                    "reasoning_options": [],
                                }
                            }
                        }
                    }

            return Resp()

    monkeypatch.setattr("app.models.models_dev.httpx.Client", OkClient)

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(store, "_save_disk", boom)
    source = store.refresh_now(force=True)
    assert source == "bundled"
    assert store.lookup("o3") is None
    assert store.lookup("gpt-4o") is not None
    assert store.status()["error"]
