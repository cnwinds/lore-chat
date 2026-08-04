import { describe, expect, it } from "vitest";
import {
  formatDisplayDateTime,
  formatMessageTime,
  parseStoredInstant,
  ymdInDisplayZone,
} from "./displayTime";

describe("parseStoredInstant", () => {
  it("treats naive ISO as Beijing wall time", () => {
    const d = parseStoredInstant("2026-07-10T10:00:00");
    expect(d?.toISOString()).toBe("2026-07-10T02:00:00.000Z");
  });

  it("parses explicit offset", () => {
    const d = parseStoredInstant("2026-07-10T10:00:00+08:00");
    expect(d?.toISOString()).toBe("2026-07-10T02:00:00.000Z");
  });
});

describe("formatMessageTime", () => {
  it("formats UTC instant as Beijing HH:mm", () => {
    expect(formatMessageTime("2026-07-12T06:30:00.000Z")).toBe("14:30");
  });
});

describe("formatDisplayDateTime", () => {
  it("formats naive stored time for meta panel", () => {
    expect(formatDisplayDateTime("2026-07-10T10:00:00")).toBe("2026-07-10 10:00");
  });
});

describe("ymdInDisplayZone", () => {
  it("uses Beijing calendar date", () => {
    const d = new Date("2026-07-11T20:00:00.000Z");
    expect(ymdInDisplayZone(d)).toEqual({ y: 2026, m: 7, d: 12 });
  });
});
