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
    rewritten: bool = False


@dataclass
class ExtractionResult:
    candidates: list[MemoryCandidate]
    rejected_evidence_count: int = 0
