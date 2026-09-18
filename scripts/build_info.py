#!/usr/bin/env python3
"""Compute product version for Docker build-args and CI outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.product_version import resolve, format_export_env, write_github_output  # noqa: E402


def main(argv: list[str]) -> int:
    info = resolve(repo_root=ROOT, environ={})
    if "--export-env" in argv:
        print(format_export_env(info))
        return 0
    if "--github-output" in argv:
        write_github_output(info)
        return 0
    print(json.dumps(info.as_health(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
