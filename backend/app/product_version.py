"""产品版本：发行号来自根目录 VERSION；未打 tag 的提交用 PEP 440 本地版本。

解析顺序：环境变量（镜像烘制 / --dev）→ VERSION 文件 + git。
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping

Channel = Literal["release", "development"]

_ENV_VERSION = "LORECHAT_VERSION"
_ENV_REVISION = "LORECHAT_REVISION"
_ENV_AHEAD = "LORECHAT_COMMITS_AHEAD"
_ENV_CHANNEL = "LORECHAT_CHANNEL"
_ENV_DIRTY = "LORECHAT_DIRTY"
_ENV_REPO = "LORECHAT_REPO_ROOT"

_cached: ProductVersion | None = None


@dataclass(frozen=True)
class ProductVersion:
    version: str
    revision: str
    commits_ahead: int
    channel: Channel
    display: str
    dirty: bool = False

    def as_health(self) -> dict:
        return {
            "version": self.version,
            "revision": self.revision or None,
            "commits_ahead": self.commits_ahead,
            "channel": self.channel,
            "display": self.display,
        }


def format_display(
    *,
    version: str,
    revision: str,
    commits_ahead: int,
    channel: Channel,
    dirty: bool,
) -> str:
    if channel == "release" and not dirty:
        return version
    local: list[str] = []
    if commits_ahead > 0:
        local.append(str(commits_ahead))
    if revision:
        local.append(f"g{revision}")
    if dirty:
        local.append("dirty")
    if not local:
        return version
    return f"{version}+{'.'.join(local)}"


def _clean(raw: str | None) -> str:
    return (raw or "").strip()


def _truthy(raw: str | None) -> bool:
    return _clean(raw).lower() in {"1", "true", "yes", "on"}


def _read_version_file(repo_root: Path | None) -> str:
    if repo_root is None:
        return ""
    path = repo_root / "VERSION"
    try:
        return path.read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError):
        return ""


def discover_repo_root(start: Path | None = None) -> Path | None:
    env = _clean(os.environ.get(_ENV_REPO))
    if env:
        p = Path(env)
        return p if p.is_dir() else None
    here = Path(start or __file__).resolve()
    candidates = [
        here.parent.parent.parent,  # repo: backend/app/this.py
        here.parent.parent,
        Path.cwd(),
        Path("/app"),
    ]
    seen: set[Path] = set()
    for p in candidates:
        if p in seen:
            continue
        seen.add(p)
        if (p / "VERSION").is_file() or (p / ".git").exists():
            return p
    return None


def _git(repo_root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or ""


def _from_env(environ: Mapping[str, str]) -> ProductVersion | None:
    version = _clean(environ.get(_ENV_VERSION))
    # Dockerfile / compose 默认 0.0.0 表示「未烘制」，不要盖掉 VERSION 文件。
    if not version or version == "0.0.0":
        return None
    revision = _clean(environ.get(_ENV_REVISION))
    try:
        ahead = int(_clean(environ.get(_ENV_AHEAD)) or "0")
    except ValueError:
        ahead = 0
    channel_raw = _clean(environ.get(_ENV_CHANNEL)).lower()
    dirty = _truthy(environ.get(_ENV_DIRTY))
    if channel_raw == "release" and ahead <= 0 and not dirty:
        channel: Channel = "release"
    else:
        channel = "development"
    display = format_display(
        version=version,
        revision=revision,
        commits_ahead=ahead,
        channel=channel,
        dirty=dirty,
    )
    return ProductVersion(
        version=version,
        revision=revision,
        commits_ahead=max(0, ahead),
        channel=channel,
        display=display,
        dirty=dirty,
    )


def _from_git(repo_root: Path, version: str) -> ProductVersion:
    revision = _git(repo_root, "rev-parse", "--short", "HEAD") or ""
    porcelain = _git(repo_root, "status", "--porcelain")
    dirty = bool(porcelain)
    tag = f"v{version}"
    exact = _git(repo_root, "describe", "--tags", "--exact-match")
    if exact == tag and not dirty:
        return ProductVersion(
            version=version,
            revision=revision,
            commits_ahead=0,
            channel="release",
            display=version,
            dirty=False,
        )
    ahead_s = _git(repo_root, "rev-list", "--count", f"{tag}..HEAD")
    if ahead_s is not None and ahead_s.isdigit():
        ahead = int(ahead_s)
    else:
        last = _git(repo_root, "describe", "--tags", "--abbrev=0")
        counted = (
            _git(repo_root, "rev-list", "--count", f"{last}..HEAD") if last else None
        )
        ahead = int(counted) if counted and counted.isdigit() else 0
    channel: Channel = "development"
    display = format_display(
        version=version,
        revision=revision,
        commits_ahead=ahead,
        channel=channel,
        dirty=dirty,
    )
    return ProductVersion(
        version=version,
        revision=revision,
        commits_ahead=ahead,
        channel=channel,
        display=display,
        dirty=dirty,
    )


def resolve(
    *,
    environ: Mapping[str, str] | None = None,
    repo_root: Path | None = None,
) -> ProductVersion:
    env = os.environ if environ is None else environ
    baked = _from_env(env)
    if baked is not None:
        return baked
    root = repo_root if repo_root is not None else discover_repo_root()
    version = _read_version_file(root) or "0.0.0"
    if root is not None and (root / ".git").exists():
        return _from_git(root, version)
    return ProductVersion(
        version=version,
        revision="",
        commits_ahead=0,
        channel="development",
        display=version,
        dirty=False,
    )


def get_product_version() -> ProductVersion:
    global _cached
    if _cached is None:
        _cached = resolve()
    return _cached


def reset_product_version_cache() -> None:
    global _cached
    _cached = None


def format_export_env(info: ProductVersion) -> str:
    def q(value: str) -> str:
        return "'" + value.replace("'", "'\\''") + "'"

    return "\n".join(
        [
            f"export {_ENV_VERSION}={q(info.version)}",
            f"export {_ENV_REVISION}={q(info.revision)}",
            f"export {_ENV_AHEAD}={q(str(info.commits_ahead))}",
            f"export {_ENV_CHANNEL}={q(info.channel)}",
            f"export {_ENV_DIRTY}={q('1' if info.dirty else '0')}",
        ]
    )


def write_github_output(info: ProductVersion, path: str | None = None) -> None:
    out = path or os.environ.get("GITHUB_OUTPUT")
    lines = [
        f"version={info.version}",
        f"revision={info.revision}",
        f"commits_ahead={info.commits_ahead}",
        f"channel={info.channel}",
        f"display={info.display}",
        f"dirty={'1' if info.dirty else '0'}",
    ]
    text = "\n".join(lines) + "\n"
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(text)
    else:
        print(text, end="")
