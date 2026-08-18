#!/usr/bin/env python3
"""拦截演示内容目录里的密钥、口令与构建产物。

demo/ 是从真实实例拷出来的，.kb/settings.json 含明文 API Key、
.kb/auth.json 含管理员口令哈希。这条检查是防止手滑推上公开仓库的屏障。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

FORBIDDEN_NAMES = {
    "settings.json",
    "auth.json",
    "sessions.json",
}

FORBIDDEN_SUFFIXES = (".db", ".db-wal", ".db-shm")

FORBIDDEN_PATTERNS = ("_cooldown.json",)

FORBIDDEN_DIRS = {"index"}


# 会话里可点击/预览的知识库路径（文档与 SVG）。挪文件后若不回写会话会 404。
_KB_PATH_IN_JSON = re.compile(r'"path":\s*"([^"]+\.(?:md|svg))"')
_KB_PATH_IN_TICKS = re.compile(r"`([^`\n]+\.(?:md|svg))`")


def _knowledge_docs(root: Path) -> set[str]:
    knowledge = root / "knowledge"
    if not knowledge.is_dir():
        return set()
    docs: set[str] = set()
    for path in knowledge.rglob("*"):
        if not path.is_file() or ".kb" in path.parts:
            continue
        if path.suffix.lower() in {".md", ".svg"}:
            docs.add(path.relative_to(knowledge).as_posix())
    return docs


def find_dangling_kb_refs(root: Path) -> list[str]:
    """会话 JSON 里引用了 knowledge/ 中不存在的文档路径。"""
    docs = _knowledge_docs(root)
    conv_dir = root / "conversations"
    if not conv_dir.is_dir():
        return []
    dangling: set[str] = set()
    for path in sorted(conv_dir.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        candidates = _KB_PATH_IN_JSON.findall(text) + _KB_PATH_IN_TICKS.findall(text)
        for ref in candidates:
            if "/" not in ref:
                continue
            if ref not in docs:
                dangling.add(f"{path.name}: {ref}")
    return sorted(dangling)


def find_forbidden(root: Path) -> list[Path]:
    hits: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            if path.name in FORBIDDEN_DIRS and path.parent.name == ".kb":
                hits.append(path)
            continue
        if path.name in FORBIDDEN_NAMES and ".kb" in path.parts:
            hits.append(path)
        elif path.name.endswith(FORBIDDEN_SUFFIXES):
            hits.append(path)
        elif any(path.name.endswith(p) for p in FORBIDDEN_PATTERNS):
            hits.append(path)
    return hits


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "demo")
    if not root.is_dir():
        print(f"跳过：{root} 不存在")
        return 0
    hits = find_forbidden(root)
    dangling = find_dangling_kb_refs(root)
    if not hits and not dangling:
        print(f"{root} 检查通过")
        return 0
    code = 0
    if hits:
        print("演示内容目录里出现了不该提交的文件：")
        for path in hits:
            print(f"  {path}")
        print("\nSQLite 是构建产物不是源；密钥与口令绝不进 git。")
        code = 1
    if dangling:
        print("会话引用了知识库里不存在的文档（访客点击会 404）：")
        for item in dangling:
            print(f"  {item}")
        print("\n挪文件后必须回写会话 JSON 里的路径，不要让预置时间线指向已搬走的文档。")
        code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
