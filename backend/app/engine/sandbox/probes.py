"""结构化探针：沙箱内只输出一行带标记的 JSON，宿主侧用纯函数解码并分型。

不解析 ``ls`` 等人读输出；FakeRuntime 与 OpenSandboxRuntime 共用本模块。
"""

from __future__ import annotations

import base64
import errno as errno_mod
import json
import shlex

from app.engine.sandbox.protocol import (
    CommandResult,
    DirEntry,
    SandboxFsError,
    SandboxNotADirectory,
    SandboxNotFound,
    SandboxPermissionDenied,
)

PROBE_MARK = "@@lorechat-probe@@"

LIST_DIR_SCRIPT = """\
import json, os, sys
p = sys.argv[1]
try:
    out = []
    with os.scandir(p) as it:
        for e in it:
            try:
                d = e.is_dir()
            except OSError:
                d = False
            out.append({"name": e.name, "is_dir": d})
    doc = {"ok": True, "entries": out}
except OSError as e:
    doc = {"ok": False, "errno": e.errno, "detail": e.strerror or str(e)}
sys.stdout.write("MARK" + json.dumps(doc) + "\\n")
""".replace("MARK", PROBE_MARK)

READ_B64_SCRIPT = """\
import base64, json, sys
p, n = sys.argv[1], int(sys.argv[2])
try:
    with open(p, "rb") as f:
        d = f.read(n) if n > 0 else f.read()
    doc = {"ok": True, "b64": base64.b64encode(d).decode("ascii")}
except OSError as e:
    doc = {"ok": False, "errno": e.errno, "detail": e.strerror or str(e)}
sys.stdout.write("MARK" + json.dumps(doc) + "\\n")
""".replace("MARK", PROBE_MARK)

# 按沙箱自身时钟回溯 age 秒，避免宿主与容器时钟偏差；
# 跳过隐藏目录与缓存，以及其它会话 / 定时任务的专属目录；
# 先走 conversations / schedules（已收窄到本会话），扫描上限不会被大构建目录先耗尽
WORKSPACE_OUTPUTS_SCRIPT = """\
import json, os, stat, sys, time
c = json.loads(sys.argv[1])
root = c["root"]
since = time.time() - float(c["age"])
own = {"conversations": c.get("conv"), "schedules": c.get("sched")}
skip = set(c.get("skip") or [])
hits, scanned, full = [], 0, False
for d, dirs, files in os.walk(root):
    rel = os.path.relpath(d, root)
    parts = [] if rel == "." else rel.split(os.sep)
    dirs[:] = sorted(
        (
            n for n in dirs
            if not n.startswith(".") and n not in skip
            and not (len(parts) == 1 and parts[0] in own and n != own[parts[0]])
        ),
        key=lambda n: (not (not parts and n in own), n),
    )
    for n in files:
        scanned += 1
        if scanned > c["scan"]:
            full = True
            break
        if n.startswith("."):
            continue
        p = os.path.join(d, n)
        try:
            st = os.lstat(p)
        except OSError:
            continue
        if stat.S_ISREG(st.st_mode) and st.st_mtime >= since:
            hits.append((st.st_mtime, p, st.st_size))
    if full:
        break
hits.sort(reverse=True)
doc = {
    "ok": True,
    "files": [{"path": p, "size": s} for _, p, s in hits[: c["limit"]]],
    "truncated": full or len(hits) > c["limit"],
}
sys.stdout.write("MARK" + json.dumps(doc) + "\\n")
""".replace("MARK", PROBE_MARK)

WORKSPACE_ROOT = "/workspace"
WORKSPACE_OUTPUTS_SKIP = ("node_modules", "__pycache__")
WORKSPACE_OUTPUTS_LIMIT = 20
WORKSPACE_OUTPUTS_SCAN = 20000


def workspace_outputs_config(
    *,
    age_sec: float,
    conversation_id: str | None = None,
    schedule_id: str | None = None,
    root: str = WORKSPACE_ROOT,
    limit: int = WORKSPACE_OUTPUTS_LIMIT,
    scan: int = WORKSPACE_OUTPUTS_SCAN,
) -> dict:
    return {
        "root": root,
        "age": max(0.0, float(age_sec)),
        "conv": conversation_id,
        "sched": schedule_id,
        "skip": list(WORKSPACE_OUTPUTS_SKIP),
        "limit": int(limit),
        "scan": int(scan),
    }


def workspace_outputs_command(config: dict) -> str:
    return (
        f"python3 -c {shlex.quote(WORKSPACE_OUTPUTS_SCRIPT)} "
        f"{shlex.quote(json.dumps(config))}"
    )


def list_dir_command(path: str) -> str:
    return f"python3 -c {shlex.quote(LIST_DIR_SCRIPT)} {shlex.quote(path)}"


def read_b64_command(path: str, limit: int) -> str:
    return (
        f"python3 -c {shlex.quote(READ_B64_SCRIPT)} "
        f"{shlex.quote(path)} {int(limit)}"
    )


def probe_line(doc: dict) -> str:
    """探针输出的一行（Fake 模拟沙箱时用）。"""
    return PROBE_MARK + json.dumps(doc) + "\n"


def error_from_errno(path: str, code: int | None, detail: str = "") -> SandboxFsError:
    if code == errno_mod.ENOENT:
        return SandboxNotFound(path, detail)
    if code == errno_mod.ENOTDIR:
        return SandboxNotADirectory(path, detail)
    if code in (errno_mod.EACCES, errno_mod.EPERM):
        return SandboxPermissionDenied(path, detail)
    return SandboxFsError(path, detail or f"errno={code}")


def _probe_doc(path: str, result: CommandResult) -> dict:
    # output 为 stdout/stderr 合流，解释器告警等可能混在前面；只认带标记的最后一行
    for line in reversed((result.output or "").splitlines()):
        if not line.startswith(PROBE_MARK):
            continue
        try:
            doc = json.loads(line[len(PROBE_MARK) :])
        except ValueError:
            break
        if isinstance(doc, dict):
            return doc
        break
    tail = (result.output or "").strip()[-300:]
    raise SandboxFsError(
        path,
        f"探针无有效输出 exit={result.exit_code}" + (f"：{tail}" if tail else ""),
    )


def _raise_if_failed(path: str, doc: dict) -> None:
    if doc.get("ok"):
        return
    raise error_from_errno(path, doc.get("errno"), str(doc.get("detail") or ""))


def decode_list_dir(path: str, result: CommandResult) -> list[DirEntry]:
    doc = _probe_doc(path, result)
    _raise_if_failed(path, doc)
    base = path.rstrip("/")
    entries = [
        DirEntry(
            name=str(e["name"]),
            path=f"{base}/{e['name']}",
            is_dir=bool(e.get("is_dir")),
        )
        for e in doc.get("entries") or []
        if isinstance(e, dict) and e.get("name")
    ]
    entries.sort(key=lambda e: e.name)
    return entries


def decode_read_b64(path: str, result: CommandResult) -> bytes:
    doc = _probe_doc(path, result)
    _raise_if_failed(path, doc)
    try:
        return base64.b64decode(doc.get("b64") or "", validate=True)
    except ValueError as e:
        raise SandboxFsError(path, f"base64 解码失败：{e}") from e


def decode_workspace_outputs(result: CommandResult) -> dict:
    """``{"files": [{"path", "size"}], "truncated": bool}``，按修改时间新→旧。"""
    doc = _probe_doc(WORKSPACE_ROOT, result)
    _raise_if_failed(WORKSPACE_ROOT, doc)
    files = [
        {"path": str(f["path"]), "size": int(f.get("size") or 0)}
        for f in doc.get("files") or []
        if isinstance(f, dict) and f.get("path")
    ]
    return {"files": files, "truncated": bool(doc.get("truncated"))}


def classify_sdk_fs_error(path: str, exc: BaseException) -> SandboxFsError | None:
    """把 OpenSandbox 文件 API 异常映射为分型错误；沙箱级错误返回 None 交给重建逻辑。"""
    err = getattr(exc, "error", None)
    code = str(getattr(err, "code", "") or "")
    if "SANDBOX_NOT_FOUND" in code:
        return None
    message = str(getattr(err, "message", "") or exc)
    if code.endswith("FILE_NOT_FOUND"):
        return SandboxNotFound(path, message)
    if not code or "CONNECTION" in code:
        return None
    # execd 对 ENOTDIR / EACCES / ENOENT 只给 RUNTIME_ERROR + Go syscall 错误文本
    low = message.lower()
    if "not a directory" in low:
        return SandboxNotADirectory(path, message)
    if "permission denied" in low:
        return SandboxPermissionDenied(path, message)
    if "no such file or directory" in low or "file not found" in low:
        return SandboxNotFound(path, message)
    return None


__all__ = [
    "LIST_DIR_SCRIPT",
    "PROBE_MARK",
    "READ_B64_SCRIPT",
    "WORKSPACE_OUTPUTS_SCRIPT",
    "classify_sdk_fs_error",
    "decode_list_dir",
    "decode_read_b64",
    "decode_workspace_outputs",
    "error_from_errno",
    "list_dir_command",
    "probe_line",
    "read_b64_command",
    "workspace_outputs_command",
    "workspace_outputs_config",
]
