import { describe, expect, it } from "vitest";
import { rolePersonaPreview } from "./roleListPreview";

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
