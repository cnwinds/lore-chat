import { describe, expect, it } from "vitest";
import { updateTimeline } from "./api";

describe("updateTimeline think_delta", () => {
  it("appends think blocks and merges consecutive deltas", () => {
    let timeline = updateTimeline([], "think_delta", {
      delta: "先分析",
      ts: "t1",
    });
    timeline = updateTimeline(timeline, "think_delta", {
      delta: "用户意图",
      ts: "t1",
    });
    expect(timeline).toEqual([
      { type: "think", ts: "t1", content: "先分析用户意图" },
    ]);
  });

  it("keeps think separate from text blocks", () => {
    const timeline = updateTimeline(
      [{ type: "think", ts: "t1", content: "思考" }],
      "text_delta",
      { delta: "回答", ts: "t2" },
    );
    expect(timeline).toHaveLength(2);
    expect(timeline[1]).toEqual({ type: "text", ts: "t2", content: "回答" });
  });
});

describe("updateTimeline user_inject", () => {
  it("inserts inject after tools and before later text", () => {
    let timeline = updateTimeline([], "tool_start", {
      id: "1",
      tool: "search_kb",
      label: "检索",
      ts: "t0",
      input: { query: "x" },
    });
    timeline = updateTimeline(timeline, "tool_result", {
      id: "1",
      summary: "ok",
      sources: [],
    });
    timeline = updateTimeline(timeline, "user_inject", {
      inject_id: "inj1",
      text: "补充一句",
      ts: "t1",
    });
    timeline = updateTimeline(timeline, "text_delta", {
      delta: "后续回答",
      ts: "t2",
    });
    expect(timeline.map((b) => b.type)).toEqual([
      "tool",
      "user_inject",
      "text",
    ]);
    expect(timeline[1]).toMatchObject({
      type: "user_inject",
      inject_id: "inj1",
      text: "补充一句",
    });
  });
});
