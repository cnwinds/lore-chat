import { describe, expect, it } from "vitest";
import {
  isMediaPath,
  MEDIA_ROOT,
  mediaGeneratedDir,
  mediaUploadDir,
} from "./kbMediaPaths";

describe("kbMediaPaths", () => {
  it("builds upload/generated year dirs under 媒体", () => {
    expect(mediaUploadDir("2026")).toBe("媒体/上传/2026");
    expect(mediaGeneratedDir("2026")).toBe("媒体/生成/2026");
    expect(MEDIA_ROOT).toBe("媒体");
    expect(isMediaPath("媒体/上传/2026/a.png")).toBe(true);
    expect(isMediaPath("未分类/a.png")).toBe(false);
  });
});
