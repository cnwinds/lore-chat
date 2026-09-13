import { describe, expect, it } from "vitest";
import {
  buildInboxItems,
  groupReplyPreview,
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

describe("buildInboxItems", () => {
  it("mixes a recent group above an older role", () => {
    const items = buildInboxItems(
      [
        {
          id: "default",
          name: "通用",
          avatar: null,
          system_prompt: "",
          is_default: true,
          sort_order: 0,
          created_at: "",
          updated_at: "",
          last_active_at: "2026-08-01T10:00:00+08:00",
        },
      ],
      [
        {
          id: "g1",
          title: "登录页",
          kind: "group",
          participant_role_ids: ["default", "game"],
          last_active_at: "2026-08-08T12:00:00+08:00",
        },
      ],
    );
    expect(items.map((item) => item.id)).toEqual(["g1", "default"]);
    expect(items[0]?.kind).toBe("group");
  });
});

describe("groupReplyPreview", () => {
  it("prefers the last message over member names", () => {
    expect(
      groupReplyPreview({
        last_reply_preview: "先改登录页",
        participant_names: ["通用", "游戏"],
      }),
    ).toBe("先改登录页");
  });

  it("falls back to member names", () => {
    expect(
      groupReplyPreview({
        last_reply_preview: "",
        participant_names: ["通用", "游戏"],
      }),
    ).toBe("通用、游戏");
  });
});
