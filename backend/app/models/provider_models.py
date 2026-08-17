"""从 OpenAI 兼容端点拉取 /models，并用 catalog JSON 附上能力。"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.models.catalog import (
    CatalogKind,
    catalog_hit_for_model_id,
    get_active_models_dev_store,
    normalize_catalog_kind,
    search_known_catalog,
)
from app.models.models_dev import CatalogHit, ModelsDevStore, is_image_gen_model

_log = logging.getLogger("lorechat.provider_models")


def normalize_provider_base_url(base_url: str) -> str:
    return (base_url or "").strip().rstrip("/")


def fetch_remote_model_ids(
    *,
    base_url: str,
    api_key: str | None,
    timeout_sec: float = 8.0,
) -> list[str]:
    """GET {base}/models → 模型 id 列表。失败抛 httpx/ValueError。"""
    root = normalize_provider_base_url(base_url)
    if not root:
        raise ValueError("base_url required")
    headers: dict[str, str] = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    with httpx.Client(timeout=timeout_sec) as client:
        resp = client.get(f"{root}/models", headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return parse_models_list_payload(data)


def parse_models_list_payload(data: Any) -> list[str]:
    """解析 OpenAI 风格 models.list 响应。"""
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("data")
        if rows is None and isinstance(data.get("models"), list):
            rows = data["models"]
        if rows is None:
            raise ValueError("models response missing data")
    else:
        raise ValueError("models response is not an object")
    if not isinstance(rows, list):
        raise ValueError("models data is not a list")
    out: list[str] = []
    seen: set[str] = set()
    for row in rows:
        mid = ""
        if isinstance(row, str):
            mid = row.strip()
        elif isinstance(row, dict):
            mid = str(row.get("id") or row.get("model") or "").strip()
        if not mid:
            continue
        key = mid.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(mid)
    return out


def _filter_kind(hits: list[CatalogHit], kind: CatalogKind) -> list[CatalogHit]:
    """按大模型 / 向量 / 生图分流；未知 id 靠启发式（embedding 字段或 is_image_gen_model）。"""
    if kind == "embedding":
        return [h for h in hits if h.embedding]
    if kind == "image":
        return [h for h in hits if is_image_gen_model(h.id)]
    if kind == "llm":
        return [
            h
            for h in hits
            if not h.embedding and not is_image_gen_model(h.id)
        ]
    return hits


def _filter_query(hits: list[CatalogHit], q: str) -> list[CatalogHit]:
    needle = (q or "").strip().lower()
    if not needle:
        return hits
    return [
        h
        for h in hits
        if needle in h.id.lower()
        or needle in (h.name or "").lower()
        or needle in (h.provider or "").lower()
    ]


def list_provider_models(
    *,
    base_url: str,
    api_key: str | None,
    q: str = "",
    kind: str = "llm",
    limit: int = 100,
    models_dev: ModelsDevStore | None = None,
    timeout_sec: float = 8.0,
) -> dict[str, Any]:
    """优先拉远端 /models，再按 kind 过滤大模型或向量模型；失败则回退已知目录（同 kind）。

    不在 JSON 中的 id 仍会列出，只要启发式判定类型匹配；JSON 用于能力标注与已知 embedding 标记。
    """
    limit_n = max(1, min(int(limit), 200))
    kind_norm: CatalogKind = normalize_catalog_kind(kind, default="llm")
    store = models_dev if models_dev is not None else get_active_models_dev_store()
    error: str | None = None
    source = "provider"
    hits: list[CatalogHit] = []
    try:
        ids = fetch_remote_model_ids(
            base_url=base_url, api_key=api_key, timeout_sec=timeout_sec
        )
        hits = [
            catalog_hit_for_model_id(mid, base_url=base_url, models_dev=store)
            for mid in ids
        ]
        hits = _filter_kind(hits, kind_norm)
        hits = _filter_query(hits, q)[:limit_n]
    except Exception as e:
        error = str(e)
        _log.info("provider models fetch failed, fallback to catalog: %s", e)
        source = "catalog_fallback"
        hits = search_known_catalog(
            q, kind=kind_norm, limit=limit_n, models_dev=store
        )
    # 远端成功但无生图 id 时，回退已知目录（与拉取失败同一入口，不用硬编码名单）
    if kind_norm == "image" and not hits:
        source = "catalog_fallback"
        hits = search_known_catalog(
            q, kind="image", limit=limit_n, models_dev=store
        )
    return {
        "ok": True,
        "source": source,
        "error": error,
        "kind": kind_norm,
        "items": [h.to_dict() for h in hits],
    }
