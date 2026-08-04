import { describe, expect, it } from "vitest";
import { joinKbDirectory, targetDirectoryForDrop } from "./droppedFiles";

describe("targetDirectoryForDrop", () => {
  it("maps nested relative path under base directory", () => {
    expect(targetDirectoryForDrop("项目", "资料包/子/a.md")).toEqual({
      directory: "项目/资料包/子",
      filename: "a.md",
    });
  });

  it("uses base only for loose file", () => {
    expect(targetDirectoryForDrop("项目", "readme.md")).toEqual({
      directory: "项目",
      filename: "readme.md",
    });
  });

  it("preserves folder name at root drop", () => {
    expect(targetDirectoryForDrop("", "MyFolder/x.txt")).toEqual({
      directory: "MyFolder",
      filename: "x.txt",
    });
  });
});

describe("joinKbDirectory", () => {
  it("joins without duplicate slashes", () => {
    expect(joinKbDirectory("a/", "/b/c")).toBe("a/b/c");
  });
});
