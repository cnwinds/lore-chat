import { describe, expect, it } from "vitest";
import type { ChatMessage, TimelineBlock } from "../api";
import { mergeServerTimeline } from "./timelineStream";

describe("mergeServerTimeline", () => {
  it("preserves client started_at_ms when server omits it", () => {
    const prev: ChatMessage = {
      role: "assistant",
      text: "hi",
      ts: "t0",
      timeline: [
        {
          type: "tool",
          id: "t1",
          tool: "sandbox_run",
          label: "沙箱",
          ts: "t1",
          status: "running",
          started_at_ms: 111,
        },
      ],
    };
    const incoming: TimelineBlock[] = [
      {
        type: "tool",
        id: "t1",
        tool: "sandbox_run",
        label: "沙箱",
        ts: "t1",
        status: "done",
        summary: "ok",
      },
    ];
    const next = mergeServerTimeline(prev, incoming, "done text");
    expect(next.text).toBe("done text");
    const tool = next.timeline?.[0];
    expect(tool?.type).toBe("tool");
    if (tool?.type === "tool") {
      expect(tool.started_at_ms).toBe(111);
      expect(tool.status).toBe("done");
    }
  });
});
