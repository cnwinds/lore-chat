import { describe, expect, it } from "vitest";
import {
  buildFileTree,
  collectAncestorFolderPaths,
  collectDefaultExpandedFolderPaths,
  nextUserExpandedAfterTreeChange,
  resolveExpandedFolderPaths,
  SKILLS_DIR,
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
    expect(expanded.has(SKILLS_DIR)).toBe(false);
  });
});

describe("buildFileTree fixed folders", () => {
  it("orders 系统 then 技能 at root and injects empty 技能", () => {
    const tree = buildFileTree([`${SYSTEM_LAYER_DIR}/心法.md`, "a/x.md"]);
    expect(tree[0]?.type).toBe("folder");
    expect(tree[0]?.name).toBe(SYSTEM_LAYER_DIR);
    expect(tree[1]?.type).toBe("folder");
    expect(tree[1]?.name).toBe(SKILLS_DIR);
    expect(tree.some((n) => n.name === "a")).toBe(true);
  });
});

describe("resolveExpandedFolderPaths", () => {
  const tree = buildFileTree([
    "a/x.md",
    "a/b/y.md",
    "a/b/c/z.md",
    `${SYSTEM_LAYER_DIR}/戒律.md`,
  ]);

  it("uses defaults when nothing stored", () => {
    expect(resolveExpandedFolderPaths(tree, null)).toEqual(
      collectDefaultExpandedFolderPaths(tree),
    );
    expect(resolveExpandedFolderPaths(tree, undefined)).toEqual(
      collectDefaultExpandedFolderPaths(tree),
    );
  });

  it("restores stored paths and drops missing folders", () => {
    expect(
      resolveExpandedFolderPaths(tree, ["a/b/c", "gone", "a"]),
    ).toEqual(["a/b/c", "a"]);
  });

  it("allows empty stored list (user collapsed all)", () => {
    expect(resolveExpandedFolderPaths(tree, [])).toEqual([]);
  });
});

describe("nextUserExpandedAfterTreeChange", () => {
  it("recomputes defaults when user has not persisted", () => {
    const before = buildFileTree(["a/x.md"]);
    const after = buildFileTree(["a/x.md", "b/y.md", "a/b/c/z.md"]);
    const next = nextUserExpandedAfterTreeChange(after, ["a"], false);
    expect(next).toEqual(collectDefaultExpandedFolderPaths(after));
    expect(next).toContain("b");
    expect(next).not.toContain("a/b/c");
    // sanity: previous in-memory set is ignored when not persisted
    expect(before.length).toBeGreaterThan(0);
  });

  it("only prunes when user has persisted", () => {
    const after = buildFileTree(["a/x.md", "b/y.md"]);
    expect(
      nextUserExpandedAfterTreeChange(after, ["a", "gone", "a/b"], true),
    ).toEqual(["a"]);
  });
});

describe("collectAncestorFolderPaths", () => {
  it("collects parent folders for open files", () => {
    expect(collectAncestorFolderPaths(["a/b/c.md", "x.md"])).toEqual(
      expect.arrayContaining(["a", "a/b"]),
    );
    expect(collectAncestorFolderPaths(["x.md"])).toEqual([]);
  });
});
