import { describe, expect, it } from "vitest";
import {
  rolePersonaPreview,
  sortRolesByRecentActivity,
} from "./roleListPreview";

describe("rolePersonaPreview", () => {
  it("uses system_prompt and ignores other chatter-like fields", () => {
    expect(
      rolePersonaPreview({
        system_prompt: "  专注基本面研究\n与估值 ",
      }),
    ).toBe("专注基本面研究 与估值");
  });

  it("returns empty when there is no persona", () => {
    expect(rolePersonaPreview({ system_prompt: "" })).toBe("");
    expect(rolePersonaPreview({ system_prompt: "   " })).toBe("");
    expect(rolePersonaPreview({ system_prompt: null })).toBe("");
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
});
