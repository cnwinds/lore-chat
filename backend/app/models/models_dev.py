"""models.dev 在线目录：首次拉取、TTL 刷新、磁盘缓存、搜索与能力映射。"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.models.candidate import ImageWire, ThinkingProtocol
from app.models.effort import Effort, default_effort, supported_efforts

@dataclass(frozen=True)
class CatalogHit:
    provider: str
    id: str
    name: str
    image: bool
    thinking: bool
    effort: Effort
    effort_options: tuple[Effort, ...]
    image_wire: ImageWire
    thinking_protocol: ThinkingProtocol
    embedding: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "id": self.id,
            "name": self.name,
            "image": self.image,
            "thinking": self.thinking,
            "effort": self.effort,
            "effort_options": list(self.effort_options),
            "image_wire": self.image_wire,
            "thinking_protocol": self.thinking_protocol,
            "embedding": self.embedding,
        }


_log = logging.getLogger("lorechat.models_dev")

MODELS_DEV_URL = "https://models.dev/api.json"
DEFAULT_TTL_SEC = 24 * 3600
DEFAULT_TIMEOUT_SEC = 60.0

_SHARED: dict[str, "ModelsDevStore"] = {}
_LOCK = threading.Lock()


def infer_thinking_protocol(model_id: str, base_url: str | None = None) -> ThinkingProtocol:
    mid = (model_id or "").strip().lower()
    if mid.startswith("agnes-") or "agnes-ai.com" in (base_url or "").lower():
        return "agnes"
    if mid.startswith("deepseek-"):
        return "deepseek"
    if mid.startswith("qwen"):
        return "qwen"
    if mid.startswith(("o1", "o3", "o4")) or mid.startswith("gpt-5"):
        return "openai_kwargs"
    return "none"


def infer_image_wire(model_id: str, protocol: ThinkingProtocol) -> ImageWire:
    mid = (model_id or "").strip().lower()
    if protocol == "agnes" or mid.startswith("agnes-"):
        return "url"
    return "data"


def _modalities_has_image(modalities: Any) -> bool:
    if modalities is None:
        return False
    if isinstance(modalities, dict):
        inp = modalities.get("input") or modalities.get("inputs") or []
        if isinstance(inp, str):
            return "image" in inp.lower()
        if isinstance(inp, (list, tuple, set)):
            return any("image" in str(x).lower() for x in inp)
        return "image" in json.dumps(modalities).lower()
    if isinstance(modalities, (list, tuple, set)):
        return any("image" in str(x).lower() for x in modalities)
    return "image" in str(modalities).lower()


def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "y"}
    return False


def _is_embedding_model(model_id: str, raw: dict[str, Any]) -> bool:
    """models.dev 对 embedding 无统一 type；用 id/name/family 启发式。"""
    family = str(raw.get("family") or "").lower()
    if "embed" in family:
        return True
    blob = f"{model_id} {raw.get('name') or ''} {raw.get('description') or ''}".lower()
    if "embedding" in blob or "-embed-" in blob or blob.endswith("-embed"):
        return True
    if "embed" in model_id.lower() or "embed" in str(raw.get("name") or "").lower():
        return True
    modalities = raw.get("modalities")
    if isinstance(modalities, dict):
        out = modalities.get("output") or modalities.get("outputs") or []
        if isinstance(out, str):
            return "embed" in out.lower()
        if isinstance(out, (list, tuple, set)):
            return any("embed" in str(x).lower() for x in out)
    return False


def parse_remote_model(provider: str, model_id: str, raw: dict[str, Any]) -> CatalogHit:
    name = str(raw.get("name") or model_id)
    embedding = _is_embedding_model(model_id, raw)
    image = False if embedding else _modalities_has_image(raw.get("modalities"))
    if not embedding and not image and _as_bool(raw.get("attachment")):
        # 部分条目用 attachment 表示可挂多媒体
        image = True
    thinking = False if embedding else _as_bool(raw.get("reasoning"))
    protocol = "none" if embedding else infer_thinking_protocol(model_id)
    wire = infer_image_wire(model_id, protocol)
    opts = ("medium",) if embedding else supported_efforts(model_id, protocol)
    effort = "medium" if embedding else default_effort(model_id, protocol)
    return CatalogHit(
        provider=provider,
        id=model_id,
        name=name,
        image=image,
        thinking=thinking,
        effort=effort,
        effort_options=opts,
        image_wire=wire,
        thinking_protocol=protocol,
        embedding=embedding,
    )


def index_payload(payload: dict[str, Any]) -> dict[str, CatalogHit]:
    """provider → models → 扁平索引；同 id 后者覆盖（少见冲突）。"""
    out: dict[str, CatalogHit] = {}
    if not isinstance(payload, dict):
        return out
    for provider, meta in payload.items():
        if not isinstance(meta, dict):
            continue
        models = meta.get("models")
        if not isinstance(models, dict):
            continue
        for mid, raw in models.items():
            if not isinstance(raw, dict):
                continue
            mid_s = str(mid).strip()
            if not mid_s:
                continue
            hit = parse_remote_model(str(provider), mid_s, raw)
            key = mid_s.lower()
            out[key] = hit
            # 也索引 provider/id
            out[f"{str(provider).lower()}/{key}"] = hit
    return out


class ModelsDevStore:
    def __init__(
        self,
        cache_path: Path,
        *,
        url: str = MODELS_DEV_URL,
        ttl_sec: float = DEFAULT_TTL_SEC,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.url = url
        self.ttl_sec = ttl_sec
        self._index: dict[str, CatalogHit] = {}
        self._fetched_at: float = 0.0
        self._source: str = "empty"
        self._error: str | None = None
        self._lock = threading.Lock()
        self._load_disk()

    def _load_disk(self) -> None:
        if not self.cache_path.is_file():
            return
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            _log.warning("models.dev cache read failed: %s", e)
            return
        if not isinstance(raw, dict):
            return
        payload = raw.get("data")
        fetched = float(raw.get("fetched_at") or 0)
        if not isinstance(payload, dict):
            return
        self._index = index_payload(payload)
        self._fetched_at = fetched
        self._source = "cache"
        self._error = None

    def _save_disk(self, payload: dict[str, Any], fetched_at: float) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        blob = {"fetched_at": fetched_at, "url": self.url, "data": payload}
        tmp = self.cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(blob, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.cache_path)

    def is_stale(self, *, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        if not self._index:
            return True
        return (now - self._fetched_at) >= self.ttl_sec

    def ensure_fresh(self, *, force: bool = False, now: float | None = None) -> str:
        """必要时拉取；返回 source：remote|cache|empty。"""
        now = time.time() if now is None else now
        with self._lock:
            if not force and self._index and not self.is_stale(now=now):
                return self._source
            try:
                with httpx.Client(timeout=DEFAULT_TIMEOUT_SEC, follow_redirects=True) as client:
                    resp = client.get(self.url)
                    resp.raise_for_status()
                    payload = resp.json()
                if not isinstance(payload, dict):
                    raise ValueError("models.dev payload is not an object")
                self._index = index_payload(payload)
                self._fetched_at = now
                self._source = "remote"
                self._error = None
                self._save_disk(payload, now)
                _log.info(
                    "models.dev refreshed entries≈%d age=0",
                    len({h.id for h in self._index.values()}),
                )
                return self._source
            except Exception as e:
                self._error = str(e)[:300]
                _log.warning("models.dev fetch failed: %s", e)
                if self._index:
                    self._source = "cache"
                    return self._source
                self._source = "empty"
                return self._source

    def lookup(self, model: str) -> CatalogHit | None:
        mid = (model or "").strip().lower()
        if not mid:
            return None
        hit = self._index.get(mid)
        if hit:
            return hit
        # 允许 openai/gpt-4o 形式
        if "/" in mid:
            return self._index.get(mid)
        return None

    def search(
        self,
        query: str,
        *,
        limit: int = 40,
        kind: str | None = None,
    ) -> list[CatalogHit]:
        q = (query or "").strip().lower()
        limit = max(1, min(int(limit), 100))
        kind_n = (kind or "all").strip().lower()
        if kind_n not in {"all", "llm", "embedding", "embed"}:
            kind_n = "all"
        # 去重：同一 id 只留一条（优先无 provider 前缀的键）
        seen: dict[str, CatalogHit] = {}
        for key, hit in self._index.items():
            if "/" in key:
                continue
            seen[hit.id.lower()] = hit
        items = list(seen.values())
        if kind_n in {"embedding", "embed"}:
            items = [h for h in items if h.embedding]
        elif kind_n == "llm":
            items = [h for h in items if not h.embedding]
        if q:
            scored: list[tuple[int, CatalogHit]] = []
            for h in items:
                blob = f"{h.provider} {h.id} {h.name}".lower()
                if q not in blob:
                    continue
                # 前缀/精确更靠前
                score = 0
                if h.id.lower() == q:
                    score = 0
                elif h.id.lower().startswith(q):
                    score = 1
                elif q in h.id.lower():
                    score = 2
                else:
                    score = 3
                scored.append((score, h))
            scored.sort(key=lambda t: (t[0], t[1].id.lower()))
            return [h for _, h in scored[:limit]]
        items.sort(key=lambda h: h.id.lower())
        return items[:limit]

    def status(self) -> dict[str, Any]:
        unique = {h.id.lower() for h in self._index.values()}
        return {
            "source": self._source,
            "fetched_at": self._fetched_at,
            "stale": self.is_stale(),
            "count": len(unique),
            "error": self._error,
            "ttl_sec": self.ttl_sec,
            "url": self.url,
        }


def shared_models_dev_store(cache_path: Path) -> ModelsDevStore:
    key = str(Path(cache_path).resolve())
    with _LOCK:
        store = _SHARED.get(key)
        if store is None:
            store = ModelsDevStore(cache_path)
            _SHARED[key] = store
        return store


def models_dev_cache_path_for_kb(kb_path: Path) -> Path:
    return Path(kb_path) / ".kb" / "models_dev_cache.json"
