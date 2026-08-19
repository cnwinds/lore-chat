#!/usr/bin/env python3
"""Extract a version section from CHANGELOG.md for GitHub Releases."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"


def extract_section(text: str, version: str) -> str:
    ver = version.lstrip("v")
    heading = re.compile(rf"^## \[({re.escape(ver)})\](?:\s.*)?$", re.MULTILINE)
    match = heading.search(text)
    if not match:
        raise SystemExit(f"CHANGELOG.md has no section ## [{ver}]")
    start = match.end()
    nxt = re.search(r"^## \[", text[start:], re.MULTILINE)
    body = text[start : start + nxt.start()] if nxt else text[start:]
    link_block = re.search(r"^\[", body, re.MULTILINE)
    if link_block:
        body = body[: link_block.start()]
    body = body.strip()
    if not body:
        raise SystemExit(f"CHANGELOG.md section [{ver}] is empty")
    return f"## {ver}\n\n{body}\n"


def self_test() -> None:
    sample = """# Changelog

## [Unreleased]

- pending

## [0.1.0] - 2026-08-19

### Added

- foo

[Unreleased]: http://example/compare
[0.1.0]: http://example/tag
"""
    out = extract_section(sample, "v0.1.0")
    assert "foo" in out, out
    assert "pending" not in out
    assert "[Unreleased]" not in out
    try:
        extract_section(sample, "9.9.9")
    except SystemExit as exc:
        if "9.9.9" not in str(exc):
            raise
    else:
        raise SystemExit("expected missing version to fail")
    print("changelog_section self-test ok")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?", help="semver, with or without v prefix")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.version:
        parser.error("version required")
    sys.stdout.write(extract_section(CHANGELOG.read_text(encoding="utf-8"), args.version))


if __name__ == "__main__":
    main()
