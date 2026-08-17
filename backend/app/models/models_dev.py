"""models.dev 在线目录：内置回退、TTL 旁路刷新、磁盘缓存、搜索与能力映射。"""

from __future__ import annotations

import gzip
import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.models.candidate import ImageWire, ThinkingProtocol
from app.models.effort import Effort, parse_reasoning_options, pick_default_effort


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
# 旁路拉取短超时：目标环境可能访问不了 models.dev，勿拖住主路径
DEFAULT_TIMEOUT_SEC = 8.0

_SHARED: dict[str, "ModelsDevStore"] = {}
_LOCK = threading.Lock()


def default_bundled_path() -> Path:
    """镜像/包内默认目录；优先 gzip，兼容明文 json。"""
    base = Path(__file__).resolve().parent / "data"
    gz = base / "models_dev_api.json.gz"
    plain = base / "models_dev_api.json"
    if gz.is_file():
        return gz
    return plain


def _read_json_file(path: Path) -> Any:
    name = path.name.lower()
    if name.endswith(".json.gz") or path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(path.read_text(encoding="utf-8"))


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
    mid = (model_id or "").strip().lower()
    name = str(raw.get("name") or "").lower()
    desc = str(raw.get("description") or "").lower()
    blob = f"{mid} {name} {desc}"
    # 常见向量模型命名（含百炼 / 开源 embedding）
    markers = (
        "embedding",
        "embeddings",
        "-embed-",
        "-embed",
        "embed-",
        "text-embedding",
        "multimodal-embedding",
        "bge-",
        "gte-",
        "e5-",
        "jina-embedding",
        "nomic-embed",
        "m3e-",
        "向量",
    )
    if any(m in blob for m in markers):
        return True
    if mid.endswith("-embed") or mid.startswith("embed"):
        return True
    modalities = raw.get("modalities")
    if isinstance(modalities, dict):
        out = modalities.get("output") or modalities.get("outputs") or []
        if isinstance(out, str):
            return "embed" in out.lower()
        if isinstance(out, (list, tuple, set)):
            return any("embed" in str(x).lower() for x in out)
    return False


def is_embedding_model(model_id: str, raw: dict[str, Any] | None = None) -> bool:
    """公开：判断模型 id 是否为嵌入模型（无 raw 时仅用 id 启发式）。"""
    return _is_embedding_model(model_id, raw or {})


def is_image_gen_model(model_id: str) -> bool:
    """判断是否为文生图 / 图像生成模型（非识图多模态对话）。

    与 CatalogHit.image（输入可识图）正交；仅看模型 id 命名启发式。
    """
    mid = (model_id or "").strip().lower()
    if not mid or is_embedding_model(mid):
        return False
    markers = (
        "dall-e",
        "dalle",
        "gpt-image",
        "cogview",
        "glm-image",
        "wanx",
        "wan2.",
        "wan2-",
        "wan2_",
        "flux",
        "stable-diffusion",
        "sdxl",
        "imagen",
        "kolors",
        "seedream",
        "seededit",
        "agnes-image",
        "image-generation",
        "text2image",
        "text-to-image",
        "midjourney",
        "ideogram",
        "qwen-image",
        "hunyuan-image",
        "playground-v",
    )
    if any(m in mid for m in markers):
        return True
    if mid.endswith("-image") or "-image-" in mid or mid.startswith("image-"):
        return True
    if mid.endswith("-t2i") or "-t2i-" in mid:
        return True
    return False


def parse_remote_model(provider: str, model_id: str, raw: dict[str, Any]) -> CatalogHit:
    name = str(raw.get("name") or model_id)
    embedding = _is_embedding_model(model_id, raw)
    image = False if embedding else _modalities_has_image(raw.get("modalities"))
    if not embedding and not image and _as_bool(raw.get("attachment")):
        # 部分条目用 attachment 表示可挂多媒体
        image = True
    thinking = False if embedding else _as_bool(raw.get("reasoning"))

    proto_raw = str(raw.get("thinking_protocol") or "").strip().lower()
    if proto_raw in {"none", "openai_kwargs", "deepseek", "qwen", "agnes"}:
        protocol: ThinkingProtocol = proto_raw  # type: ignore[assignment]
    else:
        protocol = "none" if embedding else infer_thinking_protocol(model_id)

    wire_raw = str(raw.get("image_wire") or "").strip().lower()
    if wire_raw in {"data", "url"}:
        wire: ImageWire = wire_raw  # type: ignore[assignment]
    else:
        wire = infer_image_wire(model_id, protocol)

    if embedding:
        opts: tuple[Effort, ...] = ("medium",)
    elif not thinking:
        opts = ()
    else:
        # 严格使用 JSON 的 reasoning_options；空列表 = 无可选强度，不启发式补档
        opts = parse_reasoning_options(raw.get("reasoning_options"))

    effort = pick_default_effort(opts, model=model_id)
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


def unique_hits_by_id(index: dict[str, CatalogHit]) -> list[CatalogHit]:
    """同一 id 只留一条；跳过 provider/id 双键（模型 id 本身可含斜杠）。"""
    seen: dict[str, CatalogHit] = {}
    for key, hit in index.items():
        if key != hit.id.lower():
            continue
        seen[hit.id.lower()] = hit
    return list(seen.values())


def filter_catalog_hits(
    items: list[CatalogHit],
    query: str,
    *,
    limit: int = 40,
    kind: str | None = None,
) -> list[CatalogHit]:
    """按 kind / 子串查询过滤并排序截断（models.dev 与本地补充共用）。"""
    q = (query or "").strip().lower()
    limit = max(1, min(int(limit), 100))
    kind_n = (kind or "all").strip().lower()
    if kind_n not in {"all", "llm", "embedding", "embed", "image", "imagegen"}:
        kind_n = "all"
    out = list(items)
    if kind_n in {"embedding", "embed"}:
        out = [h for h in out if h.embedding]
    elif kind_n in {"image", "imagegen"}:
        out = [h for h in out if is_image_gen_model(h.id)]
    elif kind_n == "llm":
        out = [h for h in out if not h.embedding and not is_image_gen_model(h.id)]
    if q:
        scored: list[tuple[int, CatalogHit]] = []
        for h in out:
            blob = f"{h.provider} {h.id} {h.name}".lower()
            if q not in blob:
                continue
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
    out.sort(key=lambda h: h.id.lower())
    return out[:limit]


class ModelsDevStore:
    def __init__(
        self,
        cache_path: Path,
        *,
        url: str = MODELS_DEV_URL,
        ttl_sec: float = DEFAULT_TTL_SEC,
        timeout_sec: float = DEFAULT_TIMEOUT_SEC,
        bundled_path: Path | None = None,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.url = url
        self.ttl_sec = ttl_sec
        self.timeout_sec = float(timeout_sec)
        self.bundled_path = (
            Path(bundled_path) if bundled_path is not None else default_bundled_path()
        )
        self._index: dict[str, CatalogHit] = {}
        self._fetched_at: float = 0.0
        self._source: str = "empty"
        self._error: str | None = None
        self._lock = threading.Lock()
        self._refreshing = False
        self._load_disk()
        if not self._index:
            self._load_bundled()

    def _apply_payload(
        self,
        payload: dict[str, Any],
        *,
        source: str,
        fetched_at: float,
        persist: bool,
    ) -> bool:
        """应用目录快照。persist 失败则不改内存，返回 False。"""
        index = index_payload(payload)
        if persist:
            try:
                self._save_disk(payload, fetched_at)
            except OSError as e:
                _log.warning("models.dev cache write failed: %s", e)
                return False
        with self._lock:
            self._index = index
            self._fetched_at = fetched_at
            self._source = source
            self._error = None
        return True

    def _load_disk(self) -> None:
        if not self.cache_path.is_file():
            return
        try:
            raw = _read_json_file(self.cache_path)
        except (OSError, json.JSONDecodeError, EOFError) as e:
            _log.warning("models.dev cache read failed: %s", e)
            return
        if not isinstance(raw, dict):
            return
        payload = raw.get("data")
        fetched = float(raw.get("fetched_at") or 0)
        if not isinstance(payload, dict):
            return
        self._apply_payload(
            payload, source="cache", fetched_at=fetched, persist=False
        )

    def _load_bundled(self) -> None:
        path = self.bundled_path
        if not path.is_file():
            _log.warning("models.dev bundled catalog missing: %s", path)
            return
        try:
            payload = _read_json_file(path)
        except (OSError, json.JSONDecodeError, EOFError) as e:
            _log.warning("models.dev bundled read failed: %s", e)
            return
        if not isinstance(payload, dict):
            return
        # 内置快照：fetched_at=0 → is_stale，可旁路尝试在线刷新
        self._apply_payload(
            payload, source="bundled", fetched_at=0.0, persist=False
        )
        _log.info(
            "models.dev loaded bundled entries≈%d path=%s",
            len({h.id for h in self._index.values()}),
            path,
        )

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

    def schedule_refresh(self, *, force: bool = False, now: float | None = None) -> bool:
        """旁路调度网络拉取；绝不阻塞调用方。返回是否新启了刷新线程。"""
        now = time.time() if now is None else now
        with self._lock:
            if self._refreshing:
                return False
            if not force and self._index and not self.is_stale(now=now):
                return False
            self._refreshing = True
        threading.Thread(
            target=self._bg_refresh,
            kwargs={"now": now},
            name="models-dev-fetch",
            daemon=True,
        ).start()
        return True

    def _bg_refresh(self, *, now: float) -> None:
        try:
            self._fetch_remote(now=now)
        finally:
            with self._lock:
                self._refreshing = False

    def _fetch_remote(self, *, now: float) -> str:
        try:
            with httpx.Client(timeout=self.timeout_sec, follow_redirects=True) as client:
                resp = client.get(self.url)
                resp.raise_for_status()
                payload = resp.json()
            if not isinstance(payload, dict):
                raise ValueError("models.dev payload is not an object")
            if not self._apply_payload(
                payload, source="remote", fetched_at=now, persist=True
            ):
                with self._lock:
                    self._error = "cache write failed after fetch"
                    return self._source
            _log.info(
                "models.dev refreshed entries≈%d age=0",
                len({h.id for h in self._index.values()}),
            )
            return "remote"
        except Exception as e:
            err = str(e)[:300]
            with self._lock:
                self._error = err
                if not self._index:
                    self._source = "empty"
                source = self._source
            _log.warning("models.dev fetch failed: %s", e)
            return source

    def refresh_now(self, *, force: bool = False, now: float | None = None) -> str:
        """在调用方线程同步拉取（供维护循环；仍带短超时，勿用于请求路径）。"""
        now = time.time() if now is None else now
        with self._lock:
            if self._refreshing:
                return self._source
            if not force and self._index and not self.is_stale(now=now):
                return self._source
            self._refreshing = True
        try:
            return self._fetch_remote(now=now)
        finally:
            with self._lock:
                self._refreshing = False

    def ensure_fresh(self, *, force: bool = False, now: float | None = None) -> str:
        """必要时旁路拉取；立即返回当前 source，不阻塞主逻辑。"""
        self.schedule_refresh(force=force, now=now)
        with self._lock:
            return self._source

    def lookup(self, model: str) -> CatalogHit | None:
        mid = (model or "").strip().lower()
        if not mid:
            return None
        with self._lock:
            return self._index.get(mid)

    def search(
        self,
        query: str,
        *,
        limit: int = 40,
        kind: str | None = None,
    ) -> list[CatalogHit]:
        with self._lock:
            items = unique_hits_by_id(self._index)
        return filter_catalog_hits(
            items,
            query,
            limit=limit,
            kind=kind,
        )

    def status(self) -> dict[str, Any]:
        with self._lock:
            unique = {h.id.lower() for h in self._index.values()}
            return {
                "source": self._source,
                "fetched_at": self._fetched_at,
                "stale": self.is_stale(),
                "count": len(unique),
                "error": self._error,
                "ttl_sec": self.ttl_sec,
                "url": self.url,
                "timeout_sec": self.timeout_sec,
                "refreshing": self._refreshing,
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
