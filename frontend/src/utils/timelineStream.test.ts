import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChatMessage, TimelineBlock } from "../api";
import { mergeServerTimeline } from "./timelineStream";

describe("mergeServerTimeline", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

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

  it("uses server tool ts when session reload lost local started_at_ms", () => {
    // 切会话再切回：prev 来自 GET 历史，无 started_at_ms；勿用 Date.now() 重打锚点
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-29T22:30:00+08:00"));
    const toolStartedIso = "2026-08-29T22:25:00+08:00";
    const prev: ChatMessage = {
      role: "assistant",
      text: "",
      ts: "2026-08-29T22:24:00+08:00",
      timeline: [
        {
          type: "tool",
          id: "t1",
          tool: "sandbox_run",
          label: "沙箱",
          ts: toolStartedIso,
          status: "running",
        },
      ],
    };
    const incoming: TimelineBlock[] = [
      {
        type: "tool",
        id: "t1",
        tool: "sandbox_run",
        label: "沙箱",
        ts: toolStartedIso,
        status: "running",
        progress_log: ["still running"],
      },
    ];
    const next = mergeServerTimeline(prev, incoming);
    const tool = next.timeline?.[0];
    expect(tool?.type).toBe("tool");
    if (tool?.type === "tool") {
      expect(tool.started_at_ms).toBe(Date.parse(toolStartedIso));
      expect(tool.started_at_ms).not.toBe(Date.now());
    }
  });

  it("does not invent Date.now when ts is unparsable", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-29T22:30:00+08:00"));
    const prev: ChatMessage = {
      role: "assistant",
      text: "",
      ts: "t0",
      timeline: [],
    };
    const incoming: TimelineBlock[] = [
      {
        type: "tool",
        id: "t1",
        tool: "sandbox_run",
        label: "沙箱",
        ts: "not-a-date",
        status: "running",
      },
    ];
    const next = mergeServerTimeline(prev, incoming);
    const tool = next.timeline?.[0];
    expect(tool?.type).toBe("tool");
    if (tool?.type === "tool") {
      expect(tool.started_at_ms).toBeUndefined();
    }
  });

  it("stamps nested parallel children from server ts", () => {
    const iso = "2026-08-29T22:25:00+08:00";
    const prev: ChatMessage = {
      role: "assistant",
      text: "",
      ts: iso,
      timeline: [],
    };
    const incoming: TimelineBlock[] = [
      {
        type: "parallel",
        batch_id: "b1",
        ts: iso,
        children: [
          {
            type: "tool",
            id: "t1",
            tool: "sandbox_run",
            label: "沙箱",
            ts: iso,
            status: "running",
          },
        ],
      },
    ];
    const next = mergeServerTimeline(prev, incoming);
    const batch = next.timeline?.[0];
    expect(batch?.type).toBe("parallel");
    if (batch?.type === "parallel") {
      const tool = batch.children[0];
      expect(tool.type).toBe("tool");
      if (tool.type === "tool") {
        expect(tool.started_at_ms).toBe(Date.parse(iso));
      }
    }
  });
});
