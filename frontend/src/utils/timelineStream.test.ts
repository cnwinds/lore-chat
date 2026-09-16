import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChatMessage, TimelineBlock } from "../api";
import { mergeServerTimeline, updateTimeline } from "./timelineStream";

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

  it("stamps Date.now once for a running tool with unparsable ts, then keeps it", () => {
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
    const first = mergeServerTimeline(prev, incoming);
    const tool = first.timeline?.[0];
    expect(tool?.type).toBe("tool");
    if (tool?.type !== "tool") return;
    expect(tool.started_at_ms).toBe(Date.now());
    vi.setSystemTime(new Date("2026-08-29T22:31:00+08:00"));
    const second = mergeServerTimeline(first, incoming);
    const again = second.timeline?.[0];
    expect(again?.type).toBe("tool");
    if (again?.type === "tool") {
      expect(again.started_at_ms).toBe(tool.started_at_ms);
    }
  });

  it("keeps a server epoch started_at_ms from timeline_state", () => {
    const incoming: TimelineBlock[] = [
      {
        type: "tool",
        id: "t1",
        tool: "fetch_url",
        label: "打开链接",
        ts: "2026-09-16T16:00:00+08:00",
        status: "running",
        started_at_ms: 1_700_000_000_000,
      },
    ];
    const next = mergeServerTimeline(
      { role: "assistant", text: "", ts: "t0", timeline: [] },
      incoming,
    );
    const tool = next.timeline?.[0];
    expect(tool?.type).toBe("tool");
    if (tool?.type === "tool") {
      expect(tool.started_at_ms).toBe(1_700_000_000_000);
    }
  });

  it("does not treat naive Beijing ts as a future UTC instant", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-16T16:00:05+08:00"));
    const next = mergeServerTimeline(
      { role: "assistant", text: "", ts: "t0", timeline: [] },
      [
        {
          type: "tool",
          id: "t1",
          tool: "fetch_url",
          label: "打开链接",
          ts: "2026-09-16T16:00:00",
          status: "running",
        },
      ],
    );
    const tool = next.timeline?.[0];
    expect(tool?.type).toBe("tool");
    if (tool?.type === "tool") {
      expect(tool.started_at_ms).toBe(Date.parse("2026-09-16T16:00:00+08:00"));
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

describe("updateTimeline assistant_visible_set", () => {
  it("keeps think and replaces trailing text", () => {
    const timeline: TimelineBlock[] = [
      { type: "think", ts: "t0", content: "thinking" },
      { type: "text", ts: "t1", content: "前言\n\n【征询】选哪个？ 选项：A；B" },
    ];
    const next = updateTimeline(timeline, "assistant_visible_set", {
      text: "前言",
      ts: "t2",
    });
    expect(next).toHaveLength(2);
    expect(next[0]).toMatchObject({ type: "think", content: "thinking" });
    expect(next[1]).toMatchObject({ type: "text", content: "前言" });
  });

  it("drops text blocks when remainder is empty", () => {
    const timeline: TimelineBlock[] = [
      { type: "text", ts: "t0", content: "【征询】选哪个？ 选项：A；B" },
    ];
    const next = updateTimeline(timeline, "assistant_visible_set", { text: "" });
    expect(next).toEqual([]);
  });
});

describe("updateTimeline think duration", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("stamps duration_ms when text follows think", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00.000Z"));
    let timeline = updateTimeline([], "think_delta", {
      delta: "thinking",
      ts: "2026-01-01T00:00:00.000Z",
    });
    vi.setSystemTime(new Date("2026-01-01T00:00:01.500Z"));
    timeline = updateTimeline(timeline, "text_delta", {
      delta: "answer",
      ts: "2026-01-01T00:00:01.500Z",
    });
    expect(timeline[0]).toMatchObject({
      type: "think",
      content: "thinking",
      duration_ms: 1500,
    });
    expect(timeline[1]).toMatchObject({ type: "text", content: "answer" });
  });

  it("starts a new think block after the previous one was closed", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00.000Z"));
    let timeline = updateTimeline([], "think_delta", {
      delta: "first",
      ts: "2026-01-01T00:00:00.000Z",
    });
    vi.setSystemTime(new Date("2026-01-01T00:00:01.000Z"));
    timeline = updateTimeline(timeline, "tool_start", {
      id: "1",
      tool: "search_kb",
      label: "检索",
      ts: "2026-01-01T00:00:01.000Z",
    });
    timeline = updateTimeline(timeline, "think_delta", {
      delta: "second",
      ts: "2026-01-01T00:00:02.000Z",
    });
    expect(timeline.map((b) => b.type)).toEqual(["think", "tool", "think"]);
    expect(timeline[0]).toMatchObject({ duration_ms: 1000, content: "first" });
    expect(timeline[2]).toMatchObject({ content: "second" });
    expect(timeline[2].type).toBe("think");
    if (timeline[2].type === "think") {
      expect(timeline[2].duration_ms).toBeUndefined();
    }
  });

  it("does not invent duration_ms from unparsable ts without started_at_ms", () => {
    const timeline = updateTimeline(
      [{ type: "think", ts: "t0", content: "thinking" }],
      "text_delta",
      { delta: "answer", ts: "t1" },
    );
    expect(timeline[0]).toMatchObject({ type: "think", content: "thinking" });
    expect(timeline[0].type).toBe("think");
    if (timeline[0].type === "think") {
      expect(timeline[0].duration_ms).toBeUndefined();
    }
  });
});

describe("mergeServerTimeline think stopwatch", () => {
  it("preserves client started_at_ms on an open think block", () => {
    const prev: ChatMessage = {
      role: "assistant",
      text: "",
      ts: "t0",
      timeline: [
        {
          type: "think",
          ts: "2026-01-01T00:00:00.000Z",
          content: "hello",
          started_at_ms: 111,
        },
      ],
    };
    const incoming: TimelineBlock[] = [
      {
        type: "think",
        ts: "2026-01-01T00:00:00.000Z",
        content: "hello world",
      },
    ];
    const next = mergeServerTimeline(prev, incoming);
    const think = next.timeline?.[0];
    expect(think).toMatchObject({
      type: "think",
      content: "hello world",
      started_at_ms: 111,
    });
  });
});
