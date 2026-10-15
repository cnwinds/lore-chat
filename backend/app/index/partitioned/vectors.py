from __future__ import annotations

import math
import shutil
from collections.abc import Iterable, Sequence
from pathlib import Path

import numpy as np

from app.logging_config import get_logger

_log = get_logger("partitioned_index")
_DTYPE = np.dtype("<f4")


def remove_legacy_vector_dir(index_dir: str | Path) -> None:
    """删除旧 Chroma 向量目录；向量已进 partitioned.db，见 ADR 2026-10-15。"""
    path = Path(index_dir) / "vec"
    if not path.is_dir():
        return
    shutil.rmtree(path, ignore_errors=True)
    if path.exists():
        _log.warning("旧向量目录未能删净: %s", path)
    else:
        _log.info("已删除旧向量目录: %s", path)


def encode(vec: Sequence[float]) -> bytes:
    """L2 归一化后的 float32 小端字节串；余弦即点积。零向量原样存零。"""
    arr = np.asarray(vec, dtype=np.float64)
    if arr.ndim != 1 or arr.size == 0:
        raise ValueError("embedding must be a non-empty 1-D vector")
    norm = float(np.linalg.norm(arr))
    if not math.isfinite(norm):
        raise ValueError("embedding contains non-finite values")
    if norm > 0:
        arr = arr / norm
    return arr.astype(_DTYPE).tobytes()


def top_k(
    batches: Iterable[Sequence[tuple[str, str, bytes]]],
    query: Sequence[float],
    k: int,
) -> list[tuple[str, str, float]]:
    """分批精确余弦；维度与查询不符的行（旧模型残留）跳过。"""
    if k <= 0:
        return []
    q = np.frombuffer(encode(query), dtype=_DTYPE)
    width = q.size * _DTYPE.itemsize
    best: list[tuple[float, str, str]] = []
    for rows in batches:
        valid = [r for r in rows if len(r[2]) == width]
        if not valid:
            continue
        mat = np.frombuffer(b"".join(r[2] for r in valid), dtype=_DTYPE)
        scores = mat.reshape(len(valid), q.size) @ q
        n = min(k, len(valid))
        for i in np.argpartition(-scores, n - 1)[:n]:
            best.append((float(scores[i]), valid[i][0], valid[i][1]))
        best.sort(key=lambda x: -x[0])
        del best[k:]
    return [(partition, item_id, score) for score, partition, item_id in best]
