import { describe, expect, it } from "vitest";
import {
  roleReplyPreview,
  sortRolesByRecentActivity,
} from "./roleListPreview";

describe("roleReplyPreview", () => {
  it("uses the last assistant reply and ignores persona", () => {
    expect(
      roleReplyPreview({
        last_reply_preview: "  今日沪深三百震荡\n建议先看量 ",
      }),
    ).toBe("今日沪深三百震荡 建议先看量");
  });

  it("returns empty when there is no reply", () => {
    expect(roleReplyPreview({ last_reply_preview: "" })).toBe("");
    expect(roleReplyPreview({ last_reply_preview: "   " })).toBe("");
    expect(roleReplyPreview({ last_reply_preview: null })).toBe("");
  });
});

describe("sortRolesByRecentActivity", () => {
  it("puts the most recently active role first", () => {
    const sorted = sortRolesByRecentActivity([
      {
        id: "old",
        last_active_at: "2026-08-06T09:00:00+08:00",
        sort_order: 0,
      },
      {
        id: "new",
        last_active_at: "2026-08-07T20:00:00+08:00",
        sort_order: 1,
      },
    ]);
    expect(sorted.map((r) => r.id)).toEqual(["new", "old"]);
  });

  it("keeps never-chatted roles below ones that have been chatted", () => {
    const sorted = sortRolesByRecentActivity([
      {
        id: "fresh",
        last_active_at: null,
        sort_order: 0,
      },
      {
        id: "chatted",
        last_active_at: "2026-01-01T00:00:00Z",
        sort_order: 1,
      },
    ]);
    expect(sorted.map((r) => r.id)).toEqual(["chatted", "fresh"]);
  });

  it("pins a currently busy role to the top", () => {
    const sorted = sortRolesByRecentActivity(
      [
        {
          id: "idle",
          last_active_at: "2026-08-07T20:00:00+08:00",
          sort_order: 0,
        },
        {
          id: "busy",
          last_active_at: "2026-08-01T10:00:00+08:00",
          sort_order: 1,
        },
      ],
      ["busy"],
    );
    expect(sorted.map((r) => r.id)).toEqual(["busy", "idle"]);
  });
});
