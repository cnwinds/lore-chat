"""请求快照详情与类别 token 分摊。"""

from __future__ import annotations

import json
from typing import Any

from app.engine.agent.prompt_parts import category_for_kind, category_label, category_order_key
from app.engine.usage.request_log import RequestLogStore
from app.engine.usage.token_allocate import TokenLeaf, category_totals, scale_leaves
from app.engine.usage.tokens import (
    estimate_attachment_tokens,
    estimate_tokens,
    message_overhead_tokens,
)


def _tool_calls_blob(body: dict) -> str:
    parts: list[str] = []
    for tc in body.get("tool_calls") or []:
        fn = tc.get("function") or {}
        name = fn.get("name") or ""
        args = fn.get("arguments") or ""
        parts.append(f"{name}({args})")
    return "\n".join(parts)


def _parse_tool_calls(body: dict) -> list[dict] | None:
    if body.get("role") != "assistant" or not body.get("tool_calls"):
        return None
    out: list[dict] = []
    for tc in body["tool_calls"]:
        fn = tc.get("function") or {}
        args_raw = fn.get("arguments")
        if isinstance(args_raw, str):
            try:
                args_parsed = json.loads(args_raw)
            except json.JSONDecodeError:
                args_parsed = args_raw
        else:
            args_parsed = args_raw
        out.append(
            {
                "id": tc.get("id"),
                "name": fn.get("name"),
                "arguments": args_parsed,
            }
        )
    return out


def build_request_detail(
    store: RequestLogStore,
    row: Any,
    *,
    limit_tokens: int | None,
) -> dict[str, Any]:
    call_id = int(row["id"])
    bodies = store.load_message_bodies(call_id)
    tools = store.load_tools(row["tools_hash"])
    params = json.loads(row["params_json"])

    messages_out: list[dict[str, Any]] = []
    leaves: list[TokenLeaf] = []
    overhead = message_overhead_tokens()

    for idx, (body, segments) in enumerate(bodies):
        tool_calls_out = _parse_tool_calls(body)
        seg_out: list[dict[str, Any]] = []
        msg_leaf_indices: list[int] = []

        for si, s in enumerate(segments):
            est = 0
            if s.get("media"):
                path = (s.get("media") or {}).get("path") or ""
                est = estimate_attachment_tokens([path]) if path else estimate_tokens("")
            else:
                est = estimate_tokens(s.get("text") or "")
            leaf = TokenLeaf(
                category=category_for_kind(str(s.get("kind") or "unlabeled")),
                estimate=est,
                message_index=idx,
                segment_index=si,
            )
            leaves.append(leaf)
            msg_leaf_indices.append(len(leaves) - 1)
            seg_out.append(
                {
                    "kind": s["kind"],
                    "category": category_for_kind(str(s.get("kind"))),
                    "label": s["label"],
                    "text": s.get("text") or "",
                    "tokens": 0,
                    "media": s.get("media"),
                }
            )

        if tool_calls_out:
            tc_est = estimate_tokens(_tool_calls_blob(body))
            leaves.append(
                TokenLeaf(
                    category="tool_io",
                    estimate=tc_est,
                    message_index=idx,
                    is_tool_calls=True,
                )
            )
            msg_leaf_indices.append(len(leaves) - 1)

        if msg_leaf_indices:
            largest = max(msg_leaf_indices, key=lambda i: leaves[i].estimate)
            leaves[largest].estimate += overhead

        messages_out.append(
            {
                "index": idx,
                "role": body.get("role"),
                "tokens": 0,
                "segments": seg_out,
                "tool_calls": tool_calls_out,
                "tool_call_id": body.get("tool_call_id"),
            }
        )

    tools_out: list[dict[str, Any]] = []
    for ti, t in enumerate(tools):
        blob = json.dumps(t, ensure_ascii=False)
        est = estimate_tokens(blob)
        leaves.append(TokenLeaf(category="tools", estimate=est, tool_index=ti))
        tools_out.append(
            {
                "name": t.get("function", {}).get("name") or t.get("name"),
                "description": (t.get("function") or {}).get("description")
                or t.get("description"),
                "parameters": (t.get("function") or {}).get("parameters")
                or t.get("parameters")
                or {},
                "tokens": 0,
            }
        )

    measured = row["prompt_tokens"]
    total = scale_leaves(leaves, measured)
    cat_map = category_totals(leaves)

    for leaf in leaves:
        if leaf.message_index is None:
            if leaf.tool_index is not None:
                tools_out[leaf.tool_index]["tokens"] = leaf.tokens
            continue
        msg = messages_out[leaf.message_index]
        if leaf.is_tool_calls:
            msg["tokens"] += leaf.tokens
            continue
        if leaf.segment_index is not None:
            msg["segments"][leaf.segment_index]["tokens"] = leaf.tokens
        msg["tokens"] += leaf.tokens

    categories = [
        {"key": k, "label": category_label(k), "tokens": v}
        for k, v in sorted(cat_map.items(), key=lambda x: category_order_key(x[0]))
        if v > 0
    ]

    return {
        "id": call_id,
        "turn_id": row["turn_id"],
        "round": int(row["round"]),
        "ts": row["ts"],
        "status": row["status"],
        "error": row["error"],
        "attempts": int(row["attempts"]),
        "model": row["model"],
        "model_label": row["model_label"],
        "params": params,
        "usage": {
            "prompt_tokens": row["prompt_tokens"] if measured is not None else total,
            "completion_tokens": row["completion_tokens"],
            "cache_tokens": row["cache_tokens"],
        },
        "limit_tokens": limit_tokens,
        "estimated": measured is None or measured <= 0,
        "messages": messages_out,
        "tools": tools_out,
        "categories": categories,
    }
