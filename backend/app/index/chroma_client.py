from __future__ import annotations

import threading
from typing import Any

import app.sqlite_compat  # noqa: F401 — 确保 SQLite ≥ 3.35

from chromadb import PersistentClient
from chromadb.config import Settings

from app.closing import close_quietly
from app.index.chroma_repair import ensure_chroma_repaired


def make_persistent_client(path: str) -> PersistentClient:
    ensure_chroma_repaired(path)
    return PersistentClient(
        path=path,
        settings=Settings(anonymized_telemetry=False),
    )


class ThreadLocalChroma:
    """Per-thread PersistentClient; close() releases SQLite locks and blocks reopen."""

    def __init__(self, path: str, name: str, metadata: dict[str, Any]):
        self._path = path
        self._name = name
        self._metadata = metadata
        self._local = threading.local()
        self._clients_lock = threading.Lock()
        self._clients: list[Any] = []
        self._closed = False

    def collection(self):
        with self._clients_lock:
            if self._closed:
                raise RuntimeError("chroma client closed")
            col = getattr(self._local, "col", None)
            if col is not None:
                return col
        client = make_persistent_client(self._path)
        col = client.get_or_create_collection(
            name=self._name, metadata=self._metadata
        )
        with self._clients_lock:
            if self._closed:
                close_quietly(client)
                raise RuntimeError("chroma client closed")
            self._local.col = col
            self._clients.append(client)
        return col

    def close(self) -> None:
        with self._clients_lock:
            self._closed = True
            clients = list(self._clients)
            self._clients.clear()
        for client in clients:
            close_quietly(client)
        self._local.col = None
