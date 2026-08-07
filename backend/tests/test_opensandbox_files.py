"""OpenSandboxRuntime 文件读写须保持二进制完整。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from opensandbox.models.filesystem import WriteEntry

from app.engine.sandbox.opensandbox_runtime import OpenSandboxRuntime


class _FakeFiles:
    def __init__(self, store: dict[str, bytes]) -> None:
        self.store = store
        self.written: list[WriteEntry] = []
        self.read_bytes_calls: list[dict] = []

    async def read_file(self, path: str, *, encoding: str = "utf-8", **_kw) -> str:
        return self.store[path].decode(encoding)

    async def read_bytes(self, path: str, **kw) -> bytes:
        self.read_bytes_calls.append({"path": path, **kw})
        data = self.store[path]
        rh = kw.get("range_header")
        if isinstance(rh, str) and rh.startswith("bytes="):
            spec = rh.removeprefix("bytes=")
            start_s, _, end_s = spec.partition("-")
            start = int(start_s or 0)
            end = int(end_s) + 1 if end_s else len(data)
            return data[start:end]
        return data

    async def write_files(self, entries: list[WriteEntry]) -> None:
        self.written.extend(entries)
        for e in entries:
            raw = e.data
            if isinstance(raw, str):
                raw = raw.encode("utf-8")
            assert isinstance(raw, (bytes, bytearray))
            self.store[e.path] = bytes(raw)


def _runtime(tmp_path, files: _FakeFiles) -> OpenSandboxRuntime:
    rt = OpenSandboxRuntime(kb_path=tmp_path, domain="localhost")
    rt._sandbox = SimpleNamespace(files=files)
    rt._sandbox_id = "test-sb"
    # 跳过 ensure_ready 里对真实 commands 的镜像配置
    rt._applying_mirrors = True
    return rt


@pytest.mark.asyncio
async def test_read_file_uses_read_bytes_for_binary(tmp_path):
    png = b"\x89PNG\r\n\x1a\n" + bytes(range(256))
    files = _FakeFiles({"/workspace/a.png": png})
    rt = _runtime(tmp_path, files)

    out = await rt.read_file("/workspace/a.png")

    assert out == png
    assert files.read_bytes_calls[0]["path"] == "/workspace/a.png"


@pytest.mark.asyncio
async def test_read_file_respects_max_bytes(tmp_path):
    blob = b"\x00\xff" * 1000
    files = _FakeFiles({"/workspace/b.bin": blob})
    rt = _runtime(tmp_path, files)

    out = await rt.read_file("/workspace/b.bin", max_bytes=50)

    assert out == blob[:50]
    assert files.read_bytes_calls[0].get("range_header") == "bytes=0-49"


@pytest.mark.asyncio
async def test_write_file_passes_raw_bytes(tmp_path):
    png = b"\x89PNG\r\n\x1a\n\x00\xff"
    files = _FakeFiles({})
    rt = _runtime(tmp_path, files)

    await rt.write_file("/workspace/out.png", png)

    assert len(files.written) == 1
    assert files.written[0].data == png
    assert files.store["/workspace/out.png"] == png


@pytest.mark.asyncio
async def test_read_file_base64_fallback_when_no_files_api(tmp_path):
    import base64

    png = b"\x89PNG\r\n\x1a\n\x00\xff\xfe"
    rt = OpenSandboxRuntime(kb_path=tmp_path, domain="localhost")
    rt._sandbox = SimpleNamespace(files=None)
    rt._sandbox_id = "test-sb"
    rt._applying_mirrors = True

    async def fake_run(command: str, **_kw):
        from app.engine.sandbox.protocol import CommandResult

        assert "base64" in command
        return CommandResult(
            stdout=base64.b64encode(png).decode("ascii"),
            exit_code=0,
        )

    rt.run = fake_run  # type: ignore[method-assign]
    out = await rt.read_file("/workspace/a.png", max_bytes=100)
    assert out == png
