from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryCandidate:
    statement: str
    category: str
    origin: str
    confidence: float
    start_char: int
    end_char: int


@dataclass
class ExtractionResult:
    candidates: list[MemoryCandidate]
