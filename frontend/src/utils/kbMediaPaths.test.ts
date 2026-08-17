import { describe, expect, it } from "vitest";
import {
  isMediaLeafDirectory,
  isMediaPath,
  listDirectChildren,
  MEDIA_ROOT,
  mediaGeneratedDir,
  mediaUploadDir,
  yearMonth,
} from "./kbMediaPaths";

describe("kbMediaPaths", () => {
  it("builds upload/generated year-month dirs under 媒体", () => {
    expect(mediaUploadDir("2026-08")).toBe("媒体/上传/2026-08");
    expect(mediaGeneratedDir("2026-08")).toBe("媒体/生成/2026-08");
    expect(MEDIA_ROOT).toBe("媒体");
    expect(isMediaPath("媒体/上传/2026-08/a.png")).toBe(true);
    expect(isMediaPath("未分类/a.png")).toBe(false);
    expect(yearMonth(new Date("2026-08-17T01:00:00Z"))).toBe("2026-08");
  });

  it("isMediaLeafDirectory: 仅媒体下无子文件夹的目录", () => {
    expect(isMediaLeafDirectory("媒体", false)).toBe(false);
    expect(isMediaLeafDirectory("媒体/生成", true)).toBe(false);
    expect(isMediaLeafDirectory("媒体/生成/2026-08", false)).toBe(true);
    expect(isMediaLeafDirectory("备忘/图", false)).toBe(false);
  });

  it("listDirectChildren only returns immediate files", () => {
    const all = [
      "媒体/生成/2026-08/a.png",
      "媒体/生成/2026-08/b.svg",
      "媒体/生成/2026-08/nested/c.png",
      "媒体/上传/2026-08/x.jpg",
    ];
    expect(listDirectChildren("媒体/生成/2026-08", all)).toEqual([
      "媒体/生成/2026-08/a.png",
      "媒体/生成/2026-08/b.svg",
    ]);
  });
});
