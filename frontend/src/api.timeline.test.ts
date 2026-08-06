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

describe("updateTimeline tool_progress", () => {
  it("appends progress_log while tool is running", () => {
    let timeline = updateTimeline([], "tool_start", {
      id: "1",
      tool: "sandbox_run",
      label: "run",
      ts: "t0",
      input: { command: "echo hi" },
    });
    timeline = updateTimeline(timeline, "tool_progress", {
      id: "1",
      tool: "sandbox_run",
      message: "tick",
      ts: "t1",
    });
    const block = timeline[0];
    expect(block.type).toBe("tool");
    if (block.type === "tool") {
      expect(block.query).toBe("echo hi");
      expect(block.progress_log).toEqual(["tick"]);
      expect(block.summary).toBe("tick");
    }
  });

  it("concatenates streaming chunks into one buffer", () => {
    let timeline = updateTimeline([], "tool_start", {
      id: "1",
      tool: "sandbox_run",
      label: "run",
      ts: "t0",
      input: { command: "ls" },
    });
    timeline = updateTimeline(timeline, "tool_progress", {
      id: "1",
      message: "$ ls\n",
    });
    timeline = updateTimeline(timeline, "tool_progress", {
      id: "1",
      message: "a",
    });
    timeline = updateTimeline(timeline, "tool_progress", {
      id: "1",
      message: "b\n",
    });
    const block = timeline[0];
    expect(block.type).toBe("tool");
    if (block.type === "tool") {
      // 行级无尾换行时自动插入 \\n
      expect(block.progress_log).toEqual(["$ ls\na\nb\n"]);
    }
  });
});
