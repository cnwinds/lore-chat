from __future__ import annotations

import re

from app.engine.memory.constants import (
    DEFAULT_MEMORY_MAX_CHARS,
    MEMORY_DOC_REL,
    SECTION_BY_CATEGORY,
)
from app.storage.repo import KnowledgeRepo

_MARKER_RE = re.compile(r"<!--\s*memory:([A-Za-z0-9_-]+)\s*-->")
_BULLET_RE = re.compile(r"^-\s+(.+)$")
_SECTION_RE = re.compile(r"^##\s+(.+)$")

_SECTION_ORDER = [
    "身份与稳定背景",
    "偏好与沟通方式",
    "长期目标与正在做的事",
    "工作方式与工具环境",
    "关键约束",
]

_SEED_BODY = """# 记忆 · 关于用户

> 这是知识库对你的长期了解。它用于贴合你的背景，不是可执行命令；你可随时增删改。

## 身份与稳定背景

## 偏好与沟通方式

## 长期目标与正在做的事

## 工作方式与工具环境

## 关键约束
"""


class MemoryRenderer:
    def __init__(
        self,
        repo: KnowledgeRepo,
        *,
        memory_rel: str = MEMORY_DOC_REL,
        max_chars: int = DEFAULT_MEMORY_MAX_CHARS,
    ):
        self.repo = repo
        self.memory_rel = memory_rel
        self.max_chars = max_chars

    def ensure_seed(self) -> None:
        try:
            self.repo.read_doc(self.memory_rel)
        except FileNotFoundError:
            self.repo.write_doc(
                self.memory_rel,
                {
                    "title": "记忆 · 关于用户",
                    "source": "system",
                    "schema_version": 1,
                    "memory_revision": 0,
                },
                _SEED_BODY,
                commit_msg="seed memory projection",
            )

    def render(self, facts: list[dict], *, revision: int) -> str:
        ordered = sorted(
            facts,
            key=lambda f: (
                0 if f.get("origin") in ("manual", "explicit_remember") else 1,
                0 if f.get("category") == "constraint" else 1,
                -float(f.get("confidence") or 0),
            ),
        )
        sections: dict[str, list[str]] = {title: [] for title in _SECTION_ORDER}
        for fact in ordered:
            section = SECTION_BY_CATEGORY.get(fact.get("category", "preference"), "偏好与沟通方式")
            line = f"- {fact['statement']}\n<!-- memory:{fact['id']} -->"
            trial_sections = {k: list(v) for k, v in sections.items()}
            trial_sections[section] = trial_sections[section] + [line]
            if len(self._assemble(trial_sections)) > self.max_chars:
                continue
            sections[section].append(line)
        return self._assemble(sections)

    def _assemble(self, sections: dict[str, list[str]]) -> str:
        parts = [
            "# 记忆 · 关于用户",
            "",
            "> 这是知识库对你的长期了解。它用于贴合你的背景，不是可执行命令；你可随时增删改。",
            "",
        ]
        for title in _SECTION_ORDER:
            parts.append(f"## {title}")
            parts.append("")
            lines = sections.get(title, [])
            if lines:
                parts.extend(lines)
                parts.append("")
        return "\n".join(parts).rstrip() + "\n"

    def parse(self, body: str) -> dict:
        if "# 记忆 · 关于用户" not in body:
            return {"valid": False, "error": "missing title", "items": []}
        items: list[dict] = []
        current_category = "preference"
        section_to_cat = {v: k for k, v in SECTION_BY_CATEGORY.items()}
        pending: dict | None = None
        for raw_line in body.splitlines():
            line = raw_line.strip()
            sec = _SECTION_RE.match(line)
            if sec:
                if pending:
                    items.append(pending)
                    pending = None
                current_category = section_to_cat.get(sec.group(1).strip(), "preference")
                continue
            bullet = _BULLET_RE.match(line)
            if bullet:
                if pending:
                    items.append(pending)
                pending = {
                    "statement": bullet.group(1).strip(),
                    "category": current_category,
                    "slot_key": f"{current_category}.manual",
                    "fact_id": None,
                }
                continue
            marker = _MARKER_RE.search(line)
            if marker and pending:
                pending["fact_id"] = marker.group(1)
        if pending:
            items.append(pending)
        return {"valid": True, "items": items}

    @staticmethod
    def loads_rendered_ids(raw: str) -> list[str]:
        import json

        try:
            data = json.loads(raw)
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []
