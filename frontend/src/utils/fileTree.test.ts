import { describe, expect, it } from "vitest";
import {
  buildFileTree,
  collectDefaultExpandedFolderPaths,
  SYSTEM_LAYER_DIR,
} from "./fileTree";

describe("collectDefaultExpandedFolderPaths", () => {
  it("expands depth 1–2 only", () => {
    const tree = buildFileTree([
      "a/x.md",
      "a/b/y.md",
      "a/b/c/z.md",
      `${SYSTEM_LAYER_DIR}/戒律.md`,
    ]);
    const expanded = new Set(collectDefaultExpandedFolderPaths(tree));
    expect(expanded.has("a")).toBe(true);
    expect(expanded.has("a/b")).toBe(true);
    expect(expanded.has("a/b/c")).toBe(false);
    expect(expanded.has(SYSTEM_LAYER_DIR)).toBe(false);
  });
});
