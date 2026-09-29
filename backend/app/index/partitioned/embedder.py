from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class EmbedBatch:
    vectors: list[list[float]]
    model: str


@runtime_checkable
class Embedder(Protocol):
    def embed(self, texts: list[str]) -> EmbedBatch: ...


class LLMEmbedder:
    def __init__(self, llm):
        self.llm = llm

    def embed(self, texts: list[str]) -> EmbedBatch:
        embed_with_model = getattr(self.llm, "embed_with_model", None)
        if embed_with_model is not None:
            result = embed_with_model(texts)
            if (
                not isinstance(result, tuple)
                or len(result) != 2
                or not isinstance(result[0], list)
                or not isinstance(result[1], str)
            ):
                raise TypeError(
                    "embed_with_model must return (list[list[float]], str)"
                )
            vectors, model = result
        else:
            vectors = self.llm.embed(texts)
            model = "unknown"
        if len(vectors) != len(texts):
            raise ValueError("embed vector count mismatch")
        return EmbedBatch(vectors=vectors, model=model)


class QueryEmbedCache:
    def __init__(self, maxsize: int = 256):
        self._maxsize = maxsize
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, EmbedBatch] = OrderedDict()

    def get(self, text: str) -> EmbedBatch | None:
        with self._lock:
            batch = self._cache.get(text)
            if batch is not None:
                self._cache.move_to_end(text)
            return batch

    def put(self, text: str, batch: EmbedBatch) -> None:
        with self._lock:
            if text in self._cache:
                self._cache.move_to_end(text)
            self._cache[text] = batch
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
