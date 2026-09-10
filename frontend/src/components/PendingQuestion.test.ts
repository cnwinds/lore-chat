import { describe, expect, it } from "vitest";
import { sandboxRoleCaption } from "./PendingQuestion";

describe("sandboxRoleCaption", () => {
  it("shows role name and id for sandbox confirm", () => {
    expect(
      sandboxRoleCaption({
        id: "q1",
        question: "run?",
        options: [],
        payload: { kind: "sandbox_confirm", role_id: "r1", role_name: "分析" },
      }),
    ).toBe("角色：分析（r1）");
  });

  it("returns null when no role fields", () => {
    expect(
      sandboxRoleCaption({
        id: "q2",
        question: "pick",
        options: [],
      }),
    ).toBeNull();
  });
});
