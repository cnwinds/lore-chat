from __future__ import annotations

from app.engine.source_key import extend_sources


class TimelineAccumulator:
    """从 Agent SSE 事件构建 assistant timeline 与正文。"""

    def __init__(self) -> None:
        self.timeline: list[dict] = []
        self.all_sources: list[dict] = []
        self.total_duration_ms: int | None = None
        self.assistant_text: str = ""
        self._tools: dict[str, dict] = {}
        self._parallel: dict[str, dict] = {}
        self._active_parallel: str | None = None
        self._text_block: dict | None = None
        self._think_block: dict | None = None

    def accumulate(self, event_type: str, data: dict) -> None:
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
            if isinstance(inp, dict) and inp.get("query"):
                block["query"] = inp["query"]
            self._tools[data["id"]] = block
            if self._active_parallel:
                self._parallel[self._active_parallel]["children"].append(block)
            else:
                self.timeline.append(block)
            self._text_block = None
            self._think_block = None

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
                for key in ("question_id", "question", "options", "multi_select"):
                    if data.get(key) is not None:
                        block[key] = data[key]
                for key in ("preview", "reindex_mode", "applied"):
                    if data.get(key) is not None:
                        block[key] = data[key]
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

        elif event_type == "done":
            extend_sources(self.all_sources, data.get("sources") or [])
            if data.get("total_duration_ms") is not None:
                self.total_duration_ms = data["total_duration_ms"]

    def assistant_payload(self, status: str, *, error: str | None = None) -> dict:
        assistant: dict = {
            "text": self.assistant_text,
            "timeline": self.timeline,
            "sources": self.all_sources,
            "total_duration_ms": self.total_duration_ms,
            "status": status,
        }
        if error is not None:
            assistant["error"] = error
        return assistant
