import { describe, expect, it } from "vitest";
import {
  formatDisplayDateTime,
  formatMessageTime,
  formatSidebarConversationTime,
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
  const now = new Date("2026-07-12T10:00:00+08:00");

  it("formats same-day UTC instant as Beijing HH:mm", () => {
    expect(formatMessageTime("2026-07-12T06:30:00.000Z", now)).toBe("14:30");
  });

  it("includes month/day when not today", () => {
    expect(formatMessageTime("2026-07-10T06:30:00.000Z", now)).toBe(
      "7月10日 14:30",
    );
  });

  it("includes year when crossing year boundary", () => {
    expect(formatMessageTime("2025-12-31T06:30:00.000Z", now)).toBe(
      "2025年12月31日 14:30",
    );
  });
});

describe("formatSidebarConversationTime", () => {
  const now = new Date("2026-08-07T16:00:00+08:00");

  it("always includes date and time", () => {
    expect(
      formatSidebarConversationTime("2026-08-07T15:43:00+08:00", now),
    ).toBe("8月7日 15:43");
    expect(
      formatSidebarConversationTime("2026-08-06T09:05:00+08:00", now),
    ).toBe("8月6日 09:05");
  });
});

describe("formatDisplayDateTime", () => {
  it("formats naive stored time for meta panel", () => {
    expect(formatDisplayDateTime("2026-07-10T10:00:00")).toBe("2026-07-10 10:00:00");
  });

  it("strips ISO offset to wall clock", () => {
    expect(formatDisplayDateTime("2026-08-04T14:24:40+08:00")).toBe(
      "2026-08-04 14:24:40",
    );
  });

  it("passes through wall clock strings", () => {
    expect(formatDisplayDateTime("2026-08-04 14:24:40")).toBe("2026-08-04 14:24:40");
  });
});

describe("ymdInDisplayZone", () => {
  it("uses Beijing calendar date", () => {
    const d = new Date("2026-07-11T20:00:00.000Z");
    expect(ymdInDisplayZone(d)).toEqual({ y: 2026, m: 7, d: 12 });
  });
});
