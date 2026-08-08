from __future__ import annotations

import app.sqlite_compat  # noqa: F401 — 确保 SQLite ≥ 3.35

from chromadb import PersistentClient
from chromadb.config import Settings

from app.index.chroma_repair import ensure_chroma_repaired


def make_persistent_client(path: str) -> PersistentClient:
    ensure_chroma_repaired(path)
    return PersistentClient(
        path=path,
        settings=Settings(anonymized_telemetry=False),
    )
