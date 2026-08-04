from __future__ import annotations

import json


def parse_agent_sse_event(ev: str) -> tuple[str, dict] | None:
    lines = ev.strip().split("\n")
    event_type = None
    data = None
    for line in lines:
        if line.startswith("event: "):
            event_type = line[7:]
        elif line.startswith("data: "):
            data = json.loads(line[6:])
    if event_type and data is not None:
        return event_type, data
    return None
