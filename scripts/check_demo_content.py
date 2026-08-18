#!/usr/bin/env python3
"""拦截演示内容目录里的密钥、口令与构建产物。

demo/ 是从真实实例拷出来的，.kb/settings.json 含明文 API Key、
.kb/auth.json 含管理员口令哈希。这条检查是防止手滑推上公开仓库的屏障。
"""

from __future__ import annotations

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
    if not hits:
        print(f"{root} 检查通过")
        return 0
    print("演示内容目录里出现了不该提交的文件：")
    for path in hits:
        print(f"  {path}")
    print("\nSQLite 是构建产物不是源；密钥与口令绝不进 git。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
