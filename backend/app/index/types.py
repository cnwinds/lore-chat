from dataclasses import dataclass


@dataclass
class Hit:
    doc_id: str
    chunk: str
    score: float
    source: str
