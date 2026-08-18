import { describe, expect, it } from "vitest";
import { MEMORY_DIR, SKILLS_DIR } from "../utils/fileTree";
import { resolveFolderSelect } from "./useComposerPreviewBridge";

describe("resolveFolderSelect", () => {
  it("opens memory float on click 记忆", () => {
    expect(resolveFolderSelect(MEMORY_DIR)).toEqual({ kind: "open-memory" });
    expect(resolveFolderSelect("/记忆/")).toEqual({ kind: "open-memory" });
  });

  it("ignores ctrl/meta click on 记忆 (not tray)", () => {
    expect(resolveFolderSelect(MEMORY_DIR, { ctrlKey: true })).toEqual({
      kind: "ignore",
    });
    expect(resolveFolderSelect(MEMORY_DIR, { metaKey: true })).toEqual({
      kind: "ignore",
    });
  });

  it("opens media folder for non-root media paths", () => {
    expect(resolveFolderSelect("媒体/生成/2026-08")).toEqual({
      kind: "open-media",
      path: "媒体/生成/2026-08",
    });
    expect(resolveFolderSelect("媒体")).toEqual({ kind: "none" });
    expect(resolveFolderSelect("笔记")).toEqual({ kind: "none" });
  });

  it("ctrl-click 技能 opens enabled set; other folders go to tray", () => {
    expect(resolveFolderSelect(SKILLS_DIR, { ctrlKey: true })).toEqual({
      kind: "open-skills",
    });
    expect(resolveFolderSelect("笔记", { ctrlKey: true })).toEqual({
      kind: "tray",
      path: "笔记",
    });
  });
});
