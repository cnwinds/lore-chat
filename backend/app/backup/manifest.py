from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FORMAT_VERSION = 1
APP_NAME = "lorechat"


def _read_workspace_id(kb_path: Path) -> str | None:
    path = kb_path / ".kb" / "workspace.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    wid = data.get("workspace_id")
    if isinstance(wid, str) and wid.strip():
        return wid.strip()
    return None


def build_manifest(kb_path: Path) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "app": APP_NAME,
        "includes": {
            "markdown": True,
            "attachments": True,
            "git": True,
            "kb_state": True,
        },
    }
    workspace_id = _read_workspace_id(kb_path)
    if workspace_id:
        manifest["workspace_id"] = workspace_id
    return manifest


def manifest_json(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, ensure_ascii=False, indent=2)
