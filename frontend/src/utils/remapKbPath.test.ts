import { describe, expect, it } from "vitest";
import { remapKbPath } from "./remapKbPath";

describe("remapKbPath", () => {
  it("remaps exact file path", () => {
    expect(remapKbPath("a/x.md", "a/x.md", "b/x.md")).toBe("b/x.md");
  });

  it("remaps paths under moved folder", () => {
    expect(remapKbPath("proj/sub/a.md", "proj/sub", "archive/sub")).toBe(
      "archive/sub/a.md",
    );
  });

  it("leaves unrelated paths unchanged", () => {
    expect(remapKbPath("other.md", "proj/sub", "archive/sub")).toBe("other.md");
  });
});
