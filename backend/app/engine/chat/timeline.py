from __future__ import annotations

from app.engine.chat.progress_log import append_progress_chunk
from app.engine.chat.tool_query import clip_tool_query
from app.engine.source_key import extend_sources


class TimelineAccumulator:
    """从 Agent SSE 事件构建 assistant timeline 与正文。"""

    def __init__(self) -> None:
        self.timeline: list[dict] = []
        self.all_sources: list[dict] = []
        self.total_duration_ms: int | None = None
        self.assistant_text: str = ""
        self.model_name: str | None = None
        self.model_failover: bool = False
        self._tools: dict[str, dict] = {}
        self._parallel: dict[str, dict] = {}
        self._active_parallel: str | None = None
        self._text_block: dict | None = None
        self._think_block: dict | None = None

    def accumulate(self, event_type: str, data: dict) -> None:
        if event_type == "model_selected":
            if isinstance(data.get("model"), str):
                self.model_name = data["model"]
            self.model_failover = bool(data.get("failover"))
            return

        if event_type == "tool_start":
            block = {
                "type": "tool",
                "id": data["id"],
                "tool": data["tool"],
                "label": data["label"],
                "ts": data["ts"],
                "status": "running",
            }
            inp = data.get("input")
            if isinstance(inp, dict):
                for key in ("query", "prompt", "command", "path", "sandbox_path"):
                    v = inp.get(key)
                    if isinstance(v, str):
                        q = clip_tool_query(v)
                        if q:
                            block["query"] = q
                            break
            self._tools[data["id"]] = block
            if self._active_parallel:
                self._parallel[self._active_parallel]["children"].append(block)
            else:
                self.timeline.append(block)
            self._text_block = None
            self._think_block = None

        elif event_type == "tool_progress":
            block = self._tools.get(data["id"])
            if block:
                msg = data.get("message") or ""
                log = block.setdefault("progress_log", [])
                if isinstance(log, list) and msg:
                    block["progress_log"] = append_progress_chunk(log, msg)
                    preview = msg.strip() or block.get("summary") or ""
                    if preview:
                        block["summary"] = (
                            preview if len(preview) < 200 else preview[:200] + "…"
                        )

        elif event_type == "tool_result":
            block = self._tools.get(data["id"])
            if block:
                block["status"] = "done"
                block["summary"] = data.get("summary", "")
                block["sources"] = data.get("sources") or []
                if data.get("content"):
                    block["content"] = data["content"]
                if data.get("duration_ms") is not None:
                    block["duration_ms"] = data["duration_ms"]
                if data.get("query"):
                    block["query"] = data["query"]
                for key in (
                    "question_id",
                    "question",
                    "options",
                    "multi_select",
                    "awaiting_user",
                    "awaiting_confirm",
                ):
                    if data.get(key) is not None:
                        block[key] = data[key]
                for key in ("preview", "reindex_mode", "applied"):
                    if data.get(key) is not None:
                        block[key] = data[key]
                if data.get("attachments"):
                    block["attachments"] = data["attachments"]
                # 生图轮询文案仅运行时有用；完成后与同步厂商一致，只留结果
                if block.get("tool") == "generate_image":
                    block.pop("progress_log", None)
                extend_sources(self.all_sources, block.get("sources") or [])

        elif event_type == "parallel_batch_start":
            block = {
                "type": "parallel",
                "batch_id": data["batch_id"],
                "ts": data["ts"],
                "children": [],
            }
            self._parallel[data["batch_id"]] = block
            self.timeline.append(block)
            self._active_parallel = data["batch_id"]
            self._text_block = None
            self._think_block = None

        elif event_type == "parallel_batch_end":
            block = self._parallel.get(data["batch_id"])
            if block and data.get("duration_ms") is not None:
                block["duration_ms"] = data["duration_ms"]
            if self._active_parallel == data["batch_id"]:
                self._active_parallel = None

        elif event_type == "think_delta":
            delta = data.get("delta", "")
            if self._think_block is None:
                self._think_block = {
                    "type": "think",
                    "ts": data["ts"],
                    "content": delta,
                }
                self.timeline.append(self._think_block)
            else:
                self._think_block["content"] += delta

        elif event_type == "text_delta":
            delta = data.get("delta", "")
            self.assistant_text += delta
            if self._text_block is None:
                self._text_block = {
                    "type": "text",
                    "ts": data["ts"],
                    "content": delta,
                }
                self.timeline.append(self._text_block)
            else:
                self._text_block["content"] += delta

        elif event_type == "user_inject":
            self._text_block = None
            self._think_block = None
            block = {
                "type": "user_inject",
                "inject_id": data.get("inject_id"),
                "ts": data.get("ts"),
                "text": data.get("text") or "",
            }
            if data.get("message_id"):
                block["message_id"] = data["message_id"]
            if data.get("client_message_id"):
                block["client_message_id"] = data["client_message_id"]
            if data.get("doc_context"):
                block["doc_context"] = data["doc_context"]
            if data.get("primary_doc"):
                block["primary_doc"] = data["primary_doc"]
            if data.get("attachments"):
                block["attachments"] = data["attachments"]
            self.timeline.append(block)

        elif event_type == "done":
            extend_sources(self.all_sources, data.get("sources") or [])
            if data.get("total_duration_ms") is not None:
                self.total_duration_ms = data["total_duration_ms"]

    def assistant_payload(self, status: str, *, error: str | None = None) -> dict:
        timeline = self.timeline
        if status == "interrupted":
            timeline = _mark_running_tools_interrupted(timeline)
        assistant: dict = {
            "text": self.assistant_text,
            "timeline": timeline,
            "sources": self.all_sources,
            "total_duration_ms": self.total_duration_ms,
            "status": status,
        }
        atts = collect_timeline_attachments(timeline)
        if atts:
            assistant["attachments"] = atts
        if self.model_name:
            assistant["model_name"] = self.model_name
        if self.model_failover:
            assistant["model_failover"] = True
        if error is not None:
            assistant["error"] = error
        return assistant


def collect_timeline_attachments(timeline: list[dict]) -> list[str]:
    """从时间线工具块收集 attachments（含 parallel 子块）；去重保序。"""
    out: list[str] = []
    seen: set[str] = set()

    def _add(paths: object) -> None:
        if not isinstance(paths, list):
            return
        for p in paths:
            if isinstance(p, str) and p and p not in seen:
                seen.add(p)
                out.append(p)

    for block in timeline:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool":
            _add(block.get("attachments"))
        elif block.get("type") == "parallel":
            for child in block.get("children") or []:
                if isinstance(child, dict) and child.get("type") == "tool":
                    _add(child.get("attachments"))
    return out


def _mark_running_tools_interrupted(timeline: list[dict]) -> list[dict]:
    """断流落库时，把仍 running 的工具块标为 interrupted，避免刷新后永远转圈。"""

    def patch(block: dict) -> dict:
        b = dict(block)
        if b.get("type") == "tool" and b.get("status") == "running":
            b["status"] = "interrupted"
            if not b.get("summary"):
                b["summary"] = "连接中断，未完成"
        elif b.get("type") == "parallel":
            b["children"] = [patch(c) for c in (b.get("children") or [])]
        return b

    return [patch(block) for block in timeline]
