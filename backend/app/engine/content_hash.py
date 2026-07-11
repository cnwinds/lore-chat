from __future__ import annotations

import hashlib


def normalize_body(body: str) -> str:
    return body.rstrip() + "\n"


def body_hash(body: str) -> str:
    norm = normalize_body(body)
    digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def is_body_modified(body: str, generated_hash: str) -> bool:
    return body_hash(body) != generated_hash
