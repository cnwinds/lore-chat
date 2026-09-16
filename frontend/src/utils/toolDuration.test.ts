import { describe, expect, it, vi, afterEach } from "vitest";
import { updateTimeline } from "../api";
import {
  resolveToolStartedAtMs,
  stampRunningStartedAtMs,
  thinkDisplayDurationMs,
  toolDisplayDurationMs,
} from "./toolDuration";

describe("resolveToolStartedAtMs", () => {
  it("prefers existing finite started_at_ms", () => {
    expect(resolveToolStartedAtMs("2026-08-29T22:25:00+08:00", 111)).toBe(111);
  });

  it("parses server ISO ts with offset", () => {
    const iso = "2026-08-29T22:25:00+08:00";
    expect(resolveToolStartedAtMs(iso)).toBe(Date.parse(iso));
  });

  it("treats naive ISO as Beijing wall time, not UTC", () => {
    const naive = "2026-09-16T16:00:00";
    const now = Date.parse("2026-09-16T16:00:05+08:00");
    expect(resolveToolStartedAtMs(naive, undefined, now)).toBe(
      Date.parse("2026-09-16T16:00:00+08:00"),
    );
  });

  it("rejects a start that is hours in the future", () => {
    const future = "2026-09-16T16:00:00+08:00";
    const now = Date.parse("2026-09-16T08:00:00+08:00");
    expect(resolveToolStartedAtMs(future, undefined, now)).toBeUndefined();
    expect(resolveToolStartedAtMs(undefined, Date.parse(future), now)).toBeUndefined();
  });

  it("returns undefined for unparsable ts (no Date.now fallback)", () => {
    expect(resolveToolStartedAtMs("t")).toBeUndefined();
    expect(resolveToolStartedAtMs("")).toBeUndefined();
    expect(resolveToolStartedAtMs(undefined)).toBeUndefined();
  });
});

describe("stampRunningStartedAtMs", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("covers a running tool with no usable ts using now", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-16T16:00:00+08:00"));
    expect(
      stampRunningStartedAtMs({ status: "running", ts: "not-a-date" }),
    ).toBe(Date.now());
  });

  it("does not invent a stamp for a finished tool with bad ts", () => {
    expect(
      stampRunningStartedAtMs({ status: "done", ts: "not-a-date", duration_ms: 12 } as {
        status: string;
        ts: string;
      }),
    ).toBeUndefined();
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

  it("ticks as nowMs advances", () => {
    const block = { status: "running", started_at_ms: 1000 };
    expect(toolDisplayDurationMs(block, { nowMs: 1000 })).toBe(0);
    expect(toolDisplayDurationMs(block, { nowMs: 1600 })).toBe(600);
    expect(toolDisplayDurationMs(block, { nowMs: 4500 })).toBe(3500);
  });

  it("ignores a future started_at and falls back to live elapsed", () => {
    const ms = toolDisplayDurationMs(
      { status: "running", started_at_ms: 9_999_999_999_999 },
      { nowMs: 5000, liveElapsedMs: 12_000 },
    );
    expect(ms).toBe(12_000);
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

  it("prefers server started_at_ms epoch over ts", () => {
    const timeline = updateTimeline([], "tool_start", {
      id: "1",
      tool: "fetch_url",
      label: "打开链接",
      ts: "2026-09-16T16:00:00+08:00",
      started_at_ms: 1_700_000_000_000,
      input: { url: "https://example.com" },
    });
    const block = timeline[0];
    expect(block.type).toBe("tool");
    if (block.type === "tool") {
      expect(block.started_at_ms).toBe(1_700_000_000_000);
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
