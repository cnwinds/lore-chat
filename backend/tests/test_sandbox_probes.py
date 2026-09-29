"""结构化探针：真实脚本在本机执行 + 解码 / 分型纯函数。"""

from __future__ import annotations

import errno
import os
import subprocess

import pytest

from app.engine.sandbox import probes
from app.engine.sandbox.protocol import (
    CommandResult,
    SandboxFsError,
    SandboxNotADirectory,
    SandboxNotFound,
    SandboxPermissionDenied,
)
from tests.opensandbox_fakes import sdk_api_error

_ODD_NAMES = ["a b.txt", "中文.md", "line\nbreak.txt", "-dash", "tail/"]


def _sh(command: str) -> CommandResult:
    proc = subprocess.run(
        ["bash", "-c", command], capture_output=True, text=True, check=False
    )
    return CommandResult(output=proc.stdout + proc.stderr, exit_code=proc.returncode)


def test_list_dir_script_handles_odd_names(tmp_path):
    for name in _ODD_NAMES:
        if name.endswith("/"):
            (tmp_path / name.rstrip("/")).mkdir()
        else:
            (tmp_path / name).write_text("x")

    entries = probes.decode_list_dir(str(tmp_path), _sh(probes.list_dir_command(str(tmp_path))))

    assert sorted(e.name for e in entries) == sorted(n.rstrip("/") for n in _ODD_NAMES)
    by_name = {e.name: e for e in entries}
    assert by_name["tail"].is_dir is True
    assert by_name["line\nbreak.txt"].is_dir is False
    assert by_name["a b.txt"].path == f"{tmp_path}/a b.txt"


def test_list_dir_script_classifies_missing_and_file(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("x")
    missing = str(tmp_path / "nope")

    with pytest.raises(SandboxNotFound) as ei:
        probes.decode_list_dir(missing, _sh(probes.list_dir_command(missing)))
    assert ei.value.path == missing
    with pytest.raises(SandboxNotADirectory):
        probes.decode_list_dir(str(f), _sh(probes.list_dir_command(str(f))))


@pytest.mark.skipif(os.geteuid() == 0, reason="root 不受目录权限限制")
def test_list_dir_script_classifies_permission(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        with pytest.raises(SandboxPermissionDenied):
            probes.decode_list_dir(str(locked), _sh(probes.list_dir_command(str(locked))))
    finally:
        locked.chmod(0o755)


def test_read_b64_script_roundtrip_and_limit(tmp_path):
    blob = bytes(range(256)) * 3
    p = tmp_path / "b.bin"
    p.write_bytes(blob)

    assert probes.decode_read_b64(str(p), _sh(probes.read_b64_command(str(p), 0))) == blob
    assert probes.decode_read_b64(str(p), _sh(probes.read_b64_command(str(p), 10))) == blob[:10]
    with pytest.raises(SandboxNotFound):
        missing = str(tmp_path / "nope")
        probes.decode_read_b64(missing, _sh(probes.read_b64_command(missing, 0)))


def test_decoder_ignores_noise_before_marker():
    out = "Warning: locale\n" + probes.probe_line(
        {"ok": True, "entries": [{"name": "a", "is_dir": False}]}
    )
    entries = probes.decode_list_dir("/workspace", CommandResult(output=out))
    assert [e.path for e in entries] == ["/workspace/a"]


@pytest.mark.parametrize(
    "output",
    [
        "",
        "bash: python3: command not found\n",
        probes.PROBE_MARK + "{not json\n",
        # 旧通道的症状：多行被粘成一行
        "5721a98688b9/a76572da7195/db33d98c1bc7/",
    ],
)
def test_unparseable_probe_is_runtime_error_not_absence(output):
    with pytest.raises(SandboxFsError) as ei:
        probes.decode_list_dir("/workspace", CommandResult(output=output, exit_code=127))
    assert ei.value.kind == "runtime_error"
    assert not isinstance(ei.value, SandboxNotFound)
    assert "不存在" not in ei.value.describe().split("（")[0]


@pytest.mark.parametrize(
    ("code", "cls"),
    [
        (errno.ENOENT, SandboxNotFound),
        (errno.ENOTDIR, SandboxNotADirectory),
        (errno.EACCES, SandboxPermissionDenied),
        (errno.EPERM, SandboxPermissionDenied),
    ],
)
def test_error_from_errno(code, cls):
    assert type(probes.error_from_errno("/w/x", code)) is cls


def test_error_from_unknown_errno_is_runtime_error():
    e = probes.error_from_errno("/w/x", errno.EIO, "I/O error")
    assert type(e) is SandboxFsError
    assert e.kind == "runtime_error"


@pytest.mark.parametrize(
    ("code", "message", "expected"),
    [
        ("FILE_NOT_FOUND", "file not found. open /w/x: no such file or directory", SandboxNotFound),
        ("RUNTIME_ERROR", "error accessing file: open /w/f/x: not a directory", SandboxNotADirectory),
        ("RUNTIME_ERROR", "open /w/x: permission denied", SandboxPermissionDenied),
        ("RUNTIME_ERROR", "error accessing file: file not found: /w/x", SandboxNotFound),
        ("DOCKER::SANDBOX_NOT_FOUND", "Sandbox abc not found.", None),
        ("CONNECTION", "Network connectivity error: peer closed connection", None),
        ("RUNTIME_ERROR", "disk quota exceeded", None),
    ],
)
def test_classify_sdk_fs_error(code, message, expected):
    got = probes.classify_sdk_fs_error("/w/x", sdk_api_error(code, message))
    if expected is None:
        assert got is None
    else:
        assert type(got) is expected
