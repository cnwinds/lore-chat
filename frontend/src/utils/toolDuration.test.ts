import { describe, expect, it } from "vitest";
import { updateTimeline } from "../api";
import { toolDisplayDurationMs } from "./toolDuration";

describe("toolDisplayDurationMs", () => {
  it("uses per-tool started_at while running, not stream elapsed", () => {
    const ms = toolDisplayDurationMs(
      { status: "running", started_at_ms: 1000 },
      { nowMs: 4500, liveElapsedMs: 60_000 },
    );
    expect(ms).toBe(3500);
  });

  it("uses duration_ms when done", () => {
    const ms = toolDisplayDurationMs(
      { status: "done", duration_ms: 1200, started_at_ms: 1000 },
      { nowMs: 99999, liveElapsedMs: 60_000 },
    );
    expect(ms).toBe(1200);
  });
});

describe("tool_start stamps started_at_ms", () => {
  it("sets client started_at_ms on tool_start", () => {
    const before = Date.now();
    const timeline = updateTimeline([], "tool_start", {
      id: "1",
      tool: "sandbox_run",
      label: "run",
      ts: "t0",
      input: { command: "sleep 1" },
    });
    const after = Date.now();
    const block = timeline[0];
    expect(block.type).toBe("tool");
    if (block.type === "tool") {
      expect(block.started_at_ms).toBeGreaterThanOrEqual(before);
      expect(block.started_at_ms).toBeLessThanOrEqual(after);
    }
  });
});
