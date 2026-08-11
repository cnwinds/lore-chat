"""模型冷却 / disabled 状态：落盘、错误分类、指数退避。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class ErrorClass(str, Enum):
    TRANSIENT = "transient"
    RATE_LIMIT = "rate_limit"
    AUTH = "auth"  # 401 / 坏密钥 → disabled
    CONFIG = "config"  # 模型不存在等配置错误 → disabled
    CAPABILITY = "capability"  # 本轮跳过，不冷却
    UNKNOWN = "unknown"


# 首次冷却秒数 / 上限（UNKNOWN 按 TRANSIENT）
_COOLDOWN = {
    ErrorClass.TRANSIENT: (30, 15 * 60),
    ErrorClass.RATE_LIMIT: (120, 60 * 60),
    ErrorClass.UNKNOWN: (30, 15 * 60),
}

_DISABLE_CLASSES = frozenset({ErrorClass.AUTH, ErrorClass.CONFIG})


@dataclass
class CandidateHealth:
    consecutive_failures: int = 0
    cooldown_until: float = 0.0  # epoch seconds
    disabled: bool = False
    last_error_class: str | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "consecutive_failures": self.consecutive_failures,
            "cooldown_until": self.cooldown_until,
            "disabled": self.disabled,
            "last_error_class": self.last_error_class,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CandidateHealth:
        return cls(
            consecutive_failures=int(data.get("consecutive_failures") or 0),
            cooldown_until=float(data.get("cooldown_until") or 0),
            disabled=bool(data.get("disabled")),
            last_error_class=data.get("last_error_class"),
            last_error=data.get("last_error"),
        )


def classify_error(exc: BaseException | str, *, message: str | None = None) -> ErrorClass:
    text = message if message is not None else str(exc)
    lower = text.lower()
    status = getattr(exc, "status_code", None)
    if status is None:
        body = getattr(exc, "response", None)
        status = getattr(body, "status_code", None) if body is not None else None

    if status == 401 or "invalid api key" in lower or "authentication" in lower:
        return ErrorClass.AUTH
    # 模型不存在：须绑定 model 语义，禁止裸 "does not exist"
    if status == 404 or "model_not_found" in lower or "model not found" in lower:
        return ErrorClass.CONFIG
    if "model" in lower and "does not exist" in lower:
        return ErrorClass.CONFIG
    # 限流：429 或明确配额/速率文案（含无 status 的 RateLimitError 文案）
    if (
        status == 429
        or "rate limit" in lower
        or "rate_limit" in lower
        or "ratelimit" in lower
        or "too many requests" in lower
    ):
        return ErrorClass.RATE_LIMIT
    if (
        "insufficient_quota" in lower
        or "quota exceeded" in lower
        or "exceeded your current quota" in lower
    ):
        return ErrorClass.RATE_LIMIT
    if status is not None and status >= 500:
        return ErrorClass.TRANSIENT
    if any(
        k in lower
        for k in (
            "timeout",
            "timed out",
            "connection reset",
            "connection error",
            "temporarily unavailable",
        )
    ):
        return ErrorClass.TRANSIENT
    # 缺能力：须与识图/多模态能力相关，禁止裸 "image"/"unsupported"
    if any(
        k in lower
        for k in (
            "does not support image",
            "does not support vision",
            "does not support multimodal",
            "image input is not supported",
            "vision is not supported",
            "not a vision model",
            "cannot process image",
            "invalid_image",
            "unsupported image",
            "images are not supported",
        )
    ):
        return ErrorClass.CAPABILITY
    # 本地 SDK/参数拼装错误：不应冷却远程模型
    if isinstance(exc, TypeError) and "unexpected keyword argument" in lower:
        return ErrorClass.CAPABILITY
    return ErrorClass.UNKNOWN


def cooldown_path_for_kb(kb_path: Path) -> Path:
    return Path(kb_path) / ".kb" / "model_cooldown.json"


def search_cooldown_path_for_kb(kb_path: Path) -> Path:
    return Path(kb_path) / ".kb" / "search_cooldown.json"


# 同 path 共用内存实例，避免 Container 外旁路（backfill/测试）另起一份
_SHARED: dict[str, "CooldownStore"] = {}


def shared_cooldown_store(path: Path) -> "CooldownStore":
    key = str(Path(path).resolve())
    store = _SHARED.get(key)
    if store is None:
        store = CooldownStore(path)
        _SHARED[key] = store
    return store


class CooldownStore:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._state: dict[str, CandidateHealth] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            self._state = {}
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._state = {}
            return
        if not isinstance(raw, dict):
            self._state = {}
            return
        self._state = {
            k: CandidateHealth.from_dict(v)
            for k, v in raw.items()
            if isinstance(v, dict)
        }

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: v.to_dict() for k, v in self._state.items()}
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def get(self, candidate_id: str) -> CandidateHealth:
        return self._state.get(candidate_id) or CandidateHealth()

    def is_available(self, candidate_id: str, *, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        h = self.get(candidate_id)
        if h.disabled:
            return False
        return h.cooldown_until <= now

    def record_success(self, candidate_id: str) -> None:
        h = self.get(candidate_id)
        if h.consecutive_failures == 0 and not h.disabled and h.cooldown_until == 0:
            return
        h.consecutive_failures = 0
        h.last_error = None
        h.last_error_class = None
        # 成功不清冷却剩余、不清 disabled（独立时钟）
        self._state[candidate_id] = h
        self._save()

    def record_failure(
        self,
        candidate_id: str,
        error_class: ErrorClass,
        *,
        error: str | None = None,
        now: float | None = None,
    ) -> CandidateHealth:
        now = time.time() if now is None else now
        h = self.get(candidate_id)
        h.last_error_class = error_class.value
        h.last_error = (error or "")[:500] or None

        if error_class == ErrorClass.CAPABILITY:
            self._state[candidate_id] = h
            self._save()
            return h

        if error_class in _DISABLE_CLASSES:
            h.disabled = True
            h.consecutive_failures = h.consecutive_failures + 1
            self._state[candidate_id] = h
            self._save()
            return h

        klass = error_class if error_class in _COOLDOWN else ErrorClass.TRANSIENT
        base, cap = _COOLDOWN[klass]
        h.consecutive_failures = h.consecutive_failures + 1
        delay = min(base * (2 ** (h.consecutive_failures - 1)), cap)
        h.cooldown_until = now + delay
        self._state[candidate_id] = h
        self._save()
        return h

    def clear(self, candidate_id: str | None = None) -> None:
        if candidate_id is None:
            self._state = {}
        else:
            self._state.pop(candidate_id, None)
        self._save()

    def reenable(self, candidate_id: str) -> None:
        h = self.get(candidate_id)
        h.disabled = False
        h.cooldown_until = 0
        h.consecutive_failures = 0
        h.last_error = None
        h.last_error_class = None
        self._state[candidate_id] = h
        self._save()

    def clear_disabled(self) -> None:
        """配置变更时：解除所有 disabled（保留进行中的限流冷却）。"""
        changed = False
        for cid, h in list(self._state.items()):
            if not h.disabled:
                continue
            h.disabled = False
            h.consecutive_failures = 0
            h.last_error = None
            h.last_error_class = None
            self._state[cid] = h
            changed = True
        if changed:
            self._save()

    def public_status(self, *, now: float | None = None) -> dict[str, dict[str, Any]]:
        now = time.time() if now is None else now
        out: dict[str, dict[str, Any]] = {}
        for cid, h in self._state.items():
            remaining = max(0, int(h.cooldown_until - now))
            out[cid] = {
                **h.to_dict(),
                "cooldown_remaining_sec": remaining,
                "available": (not h.disabled) and remaining == 0,
            }
        return out
