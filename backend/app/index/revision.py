from __future__ import annotations

import threading
from pathlib import Path


class IndexRevision:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.write_text("0", encoding="utf-8")

    def get(self) -> int:
        with self._lock:
            return int(self.path.read_text(encoding="utf-8").strip() or "0")

    def bump(self) -> int:
        with self._lock:
            cur = int(self.path.read_text(encoding="utf-8").strip() or "0")
            cur += 1
            self.path.write_text(str(cur), encoding="utf-8")
            return cur
