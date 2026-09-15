import { describe, expect, it, vi, afterEach } from "vitest";
import { updateTimeline } from "../api";
import {
  resolveToolStartedAtMs,
  thinkDisplayDurationMs,
  toolDisplayDurationMs,
} from "./toolDuration";

describe("resolveToolStartedAtMs", () => {
  it("prefers existing finite started_at_ms", () => {
    expect(resolveToolStartedAtMs("2026-08-29T22:25:00+08:00", 111)).toBe(111);
  });

  it("parses server ISO ts", () => {
    const iso = "2026-08-29T22:25:00+08:00";
    expect(resolveToolStartedAtMs(iso)).toBe(Date.parse(iso));
  });

  it("returns undefined for unparsable ts (no Date.now fallback)", () => {
    expect(resolveToolStartedAtMs("t")).toBeUndefined();
    expect(resolveToolStartedAtMs("")).toBeUndefined();
    expect(resolveToolStartedAtMs(undefined)).toBeUndefined();
  });
});

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

describe("thinkDisplayDurationMs", () => {
  it("uses duration_ms once the think block is closed", () => {
    expect(
      thinkDisplayDurationMs(
        { duration_ms: 1500, started_at_ms: 1000 },
        { isLive: true, nowMs: 99999 },
      ),
    ).toBe(1500);
  });

  it("uses the stopwatch while thinking is live", () => {
    expect(
      thinkDisplayDurationMs(
        { started_at_ms: 1000 },
        { isLive: true, nowMs: 2500 },
      ),
    ).toBe(1500);
  });

  it("hides duration on historical thinks without duration_ms", () => {
    expect(
      thinkDisplayDurationMs(
        { started_at_ms: 1000, ts: "t" },
        { isLive: false, nowMs: 2500 },
      ),
    ).toBeUndefined();
  });
});

describe("tool_start stamps started_at_ms", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("uses server ts when parsable", () => {
    const iso = "2026-08-29T22:25:00+08:00";
    const timeline = updateTimeline([], "tool_start", {
      id: "1",
      tool: "sandbox_run",
      label: "run",
      ts: iso,
      input: { command: "sleep 1" },
    });
    const block = timeline[0];
    expect(block.type).toBe("tool");
    if (block.type === "tool") {
      expect(block.started_at_ms).toBe(Date.parse(iso));
    }
  });

  it("falls back to Date.now when ts is unparsable", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-29T22:30:00+08:00"));
    const timeline = updateTimeline([], "tool_start", {
      id: "1",
      tool: "sandbox_run",
      label: "run",
      ts: "t0",
      input: { command: "sleep 1" },
    });
    const block = timeline[0];
    expect(block.type).toBe("tool");
    if (block.type === "tool") {
      expect(block.started_at_ms).toBe(Date.now());
    }
  });
});
