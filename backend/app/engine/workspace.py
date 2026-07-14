from __future__ import annotations

import json
import uuid
from pathlib import Path


def ensure_workspace_id(kb_path: Path) -> str:
    kb = Path(kb_path)
    path = kb / ".kb" / "workspace.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        wid = data.get("workspace_id")
        if isinstance(wid, str) and wid.strip():
            return wid.strip()
    wid = uuid.uuid4().hex
    path.write_text(
        json.dumps({"workspace_id": wid}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return wid
