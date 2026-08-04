from __future__ import annotations

import re

from app.engine.memory.models import ExtractionResult, MemoryCandidate
from app.engine.memory.normalize import infer_category
from app.engine.memory.policy import validated_candidates
from app.engine.secrets import scan_secrets

_DIRECT_PREFIXES = (
    "我偏好",
    "我喜欢",
    "我习惯",
    "我通常",
    "我一般",
    "我是",
    "我在",
    "我住在",
    "我的工作",
    "我使用",
    "我用",
)

_INFERRED_MARKERS = (
    "可能喜欢",
    "可能偏好",
    "似乎习惯",
    "看起来",
)


class RuleBasedMemoryExtractor:
    """确定性提取器：测试与无 LLM 环境使用。"""

    def extract(self, text: str, *, context_messages: list[dict] | None = None) -> ExtractionResult:
        if scan_secrets(text):
            return ExtractionResult(candidates=[])
        candidates: list[MemoryCandidate] = []
        stripped = (text or "").strip()
        if not stripped:
            return ExtractionResult(candidates=[])

        for marker in _INFERRED_MARKERS:
            idx = stripped.find(marker)
            if idx >= 0:
                stmt = stripped[idx:].split("。")[0].split("\n")[0].strip()
                if len(stmt) >= 4:
                    candidates.append(
                        MemoryCandidate(
                            statement=stmt,
                            category=infer_category(stmt),
                            origin="inferred",
                            confidence=0.65,
                            start_char=idx,
                            end_char=idx + len(stmt),
                        )
                    )
                break

        for prefix in _DIRECT_PREFIXES:
            idx = stripped.find(prefix)
            if idx >= 0:
                stmt = stripped[idx:].split("。")[0].split("\n")[0].strip()
                if len(stmt) >= 3:
                    candidates.append(
                        MemoryCandidate(
                            statement=stmt,
                            category=infer_category(stmt),
                            origin="direct",
                            confidence=0.95,
                            start_char=idx,
                            end_char=idx + len(stmt),
                        )
                    )
                break

        if not candidates and re.search(r"^我", stripped):
            candidates.append(
                MemoryCandidate(
                    statement=stripped[:120],
                    category=infer_category(stripped),
                    origin="direct",
                    confidence=0.85,
                    start_char=0,
                    end_char=min(len(stripped), 120),
                )
            )

        return ExtractionResult(
            candidates=validated_candidates(stripped, candidates[:3])
        )
