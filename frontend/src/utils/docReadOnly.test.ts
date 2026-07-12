import { describe, expect, it } from "vitest";
import { isReadOnlyPath } from "./docReadOnly";

describe("isReadOnlyPath", () => {
  it("treats .kb/ as read-only", () => {
    expect(isReadOnlyPath(".kb/conversations/x.json")).toBe(true);
  });
  it("allows normal paths", () => {
    expect(isReadOnlyPath("系统/戒律.md")).toBe(false);
  });
});
