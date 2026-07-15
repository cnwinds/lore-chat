from __future__ import annotations

from chromadb import PersistentClient
from chromadb.config import Settings


def make_persistent_client(path: str) -> PersistentClient:
    return PersistentClient(
        path=path,
        settings=Settings(anonymized_telemetry=False),
    )
