from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

_repaired_paths: set[str] = set()
_repair_lock = threading.Lock()


def repair_max_seq_id_types(path: str | Path) -> int:
    """Convert INTEGER max_seq_id rows to the 8-byte BLOB format Chroma expects."""
    db_path = Path(path) / "chroma.sqlite3"
    if not db_path.is_file():
        return 0

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT segment_id, seq_id FROM max_seq_id WHERE typeof(seq_id) = 'integer'"
        ).fetchall()
        if not rows:
            return 0
        for segment_id, seq_id in rows:
            conn.execute(
                "UPDATE max_seq_id SET seq_id = ? WHERE segment_id = ?",
                (int.to_bytes(int(seq_id), 8, "big"), segment_id),
            )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def ensure_chroma_repaired(path: str | Path) -> None:
    key = str(Path(path).resolve())
    with _repair_lock:
        if key in _repaired_paths:
            return
        repair_max_seq_id_types(key)
        _repaired_paths.add(key)
