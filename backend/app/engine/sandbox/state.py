"""持久化长驻 sandbox id（单操作者一个）。"""

from __future__ import annotations

import json
from pathlib import Path


def state_path(kb_path: Path) -> Path:
    return Path(kb_path) / ".kb" / "sandbox_runtime.json"


def load_state(kb_path: Path) -> dict:
    path = state_path(kb_path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_sandbox_id(kb_path: Path) -> str | None:
    sid = load_state(kb_path).get("sandbox_id")
    return sid if isinstance(sid, str) and sid.strip() else None


def load_mirror_region(kb_path: Path) -> str | None:
    region = load_state(kb_path).get("mirror_region")
    return region if isinstance(region, str) and region.strip() else None


def save_state(
    kb_path: Path,
    *,
    sandbox_id: str | None = None,
    mirror_region: str | None = None,
) -> None:
    path = state_path(kb_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = load_state(kb_path)
    if sandbox_id is not None:
        data["sandbox_id"] = sandbox_id
    if mirror_region is not None:
        data["mirror_region"] = mirror_region
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def save_sandbox_id(kb_path: Path, sandbox_id: str) -> None:
    save_state(kb_path, sandbox_id=sandbox_id)


def clear_sandbox_id(kb_path: Path) -> None:
    path = state_path(kb_path)
    if path.is_file():
        path.unlink()
