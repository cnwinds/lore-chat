from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FetchResult:
    url: str
    title: str = ""
    markdown: str = ""
    snippet: str = ""
    error: str | None = None
