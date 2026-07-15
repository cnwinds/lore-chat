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
