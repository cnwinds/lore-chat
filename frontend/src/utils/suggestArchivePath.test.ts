import { describe, expect, it } from "vitest";
import { suggestArchivePath } from "./suggestArchivePath";

describe("suggestArchivePath", () => {
  it("splits existing summary path", () => {
    expect(suggestArchivePath("娱乐/漫剧工具盘点.md", "hello")).toEqual({
      directory: "娱乐",
      filename: "漫剧工具盘点.md",
    });
  });

  it("defaults from first user message", () => {
    expect(suggestArchivePath(null, "有哪些漫剧工具")).toEqual({
      directory: "未分类",
      filename: "有哪些漫剧工具.md",
    });
  });
});
