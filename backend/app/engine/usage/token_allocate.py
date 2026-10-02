"""请求快照 token 分摊：统一叶子列表 + 单次缩放。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TokenLeaf:
    category: str
    estimate: int
    message_index: int | None = None
    segment_index: int | None = None
    tool_index: int | None = None
    is_tool_calls: bool = False
    tokens: int = 0


def scale_leaves(leaves: list[TokenLeaf], measured: int | None) -> int:
    """缩放全部叶子；返回总量（实测或估值和）。"""
    total_est = sum(max(0, leaf.estimate) for leaf in leaves)
    if total_est <= 0:
        for leaf in leaves:
            leaf.tokens = 0
        return 0
    target = measured if measured is not None and measured > 0 else total_est
    if measured is None or measured <= 0:
        for leaf in leaves:
            leaf.tokens = leaf.estimate
        return total_est
    scaled = [int(leaf.estimate * target / total_est) for leaf in leaves]
    drift = target - sum(scaled)
    if drift:
        order = sorted(range(len(leaves)), key=lambda i: leaves[i].estimate, reverse=True)
        for j in range(abs(drift)):
            idx = order[j % len(order)]
            scaled[idx] += 1 if drift > 0 else -1
    for i, leaf in enumerate(leaves):
        leaf.tokens = max(0, scaled[i])
    return target


def category_totals(leaves: list[TokenLeaf]) -> dict[str, int]:
    out: dict[str, int] = {}
    for leaf in leaves:
        out[leaf.category] = out.get(leaf.category, 0) + leaf.tokens
    return out
