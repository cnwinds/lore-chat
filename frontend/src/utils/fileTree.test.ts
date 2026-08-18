import { describe, expect, it } from "vitest";
import {
  buildFileTree,
  collectAncestorFolderPaths,
  collectDefaultExpandedFolderPaths,
  fileTreeFileIcon,
  isMemoryDirPath,
  isProtectedKbPath,
  isSpecialKbPath,
  MEDIA_DIR,
  MEMORY_DIR,
  nextUserExpandedAfterTreeChange,
  opensKbFloatInsteadOfExpand,
  resolveExpandedFolderPaths,
  SKILLS_DIR,
  SYSTEM_LAYER_DIR,
} from "./fileTree";

describe("isSpecialKbPath", () => {
  it("marks 系统 / 技能 / 记忆 / 媒体 trees including descendants", () => {
    expect(isSpecialKbPath(SYSTEM_LAYER_DIR)).toBe(true);
    expect(isSpecialKbPath(`${SYSTEM_LAYER_DIR}/戒律.md`)).toBe(true);
    expect(isSpecialKbPath(SKILLS_DIR)).toBe(true);
    expect(isSpecialKbPath(`${SKILLS_DIR}/demo`)).toBe(true);
    expect(isSpecialKbPath(`${SKILLS_DIR}/demo/SKILL.md`)).toBe(true);
    expect(isSpecialKbPath(MEMORY_DIR)).toBe(true);
    expect(isMemoryDirPath(`${MEMORY_DIR}/x`)).toBe(true);
    expect(isProtectedKbPath(MEMORY_DIR)).toBe(true);
    expect(isSpecialKbPath(MEDIA_DIR)).toBe(true);
    expect(isSpecialKbPath(`${MEDIA_DIR}/生成/2026-08`)).toBe(true);
    expect(isSpecialKbPath("笔记/a.md")).toBe(false);
  });
});

describe("opensKbFloatInsteadOfExpand", () => {
  it("opens 记忆根与媒体末级, not media intermediates", () => {
    expect(opensKbFloatInsteadOfExpand(MEMORY_DIR, false)).toBe(true);
    expect(opensKbFloatInsteadOfExpand(MEMORY_DIR, true)).toBe(true);
    expect(opensKbFloatInsteadOfExpand(`${MEDIA_DIR}/生成/2026-08`, false)).toBe(
      true,
    );
    expect(opensKbFloatInsteadOfExpand(`${MEDIA_DIR}/生成`, true)).toBe(false);
    expect(opensKbFloatInsteadOfExpand(MEDIA_DIR, false)).toBe(false);
    expect(opensKbFloatInsteadOfExpand("笔记", false)).toBe(false);
  });
});

describe("collectDefaultExpandedFolderPaths", () => {
  it("expands depth 1–2 only", () => {
    const tree = buildFileTree([
      "a/x.md",
      "a/b/y.md",
      "a/b/c/z.md",
      `${SYSTEM_LAYER_DIR}/戒律.md`,
      `${MEDIA_DIR}/上传/2026/a.png`,
    ]);
    const expanded = new Set(collectDefaultExpandedFolderPaths(tree));
    expect(expanded.has("a")).toBe(true);
    expect(expanded.has("a/b")).toBe(true);
    expect(expanded.has("a/b/c")).toBe(false);
    expect(expanded.has(SYSTEM_LAYER_DIR)).toBe(false);
    expect(expanded.has(MEMORY_DIR)).toBe(false);
    expect(expanded.has(MEDIA_DIR)).toBe(false);
    expect(expanded.has(`${MEDIA_DIR}/上传`)).toBe(false);
  });
});

describe("buildFileTree fixed folders", () => {
  it("orders 系统 → 技能 → 记忆 → 媒体 and injects empty media subfolders", () => {
    const tree = buildFileTree([`${SYSTEM_LAYER_DIR}/心法.md`, "a/x.md"]);
    expect(tree[0]?.type).toBe("folder");
    expect(tree[0]?.name).toBe(SYSTEM_LAYER_DIR);
    expect(tree[1]?.type).toBe("folder");
    expect(tree[1]?.name).toBe(SKILLS_DIR);
    expect(tree[2]?.type).toBe("folder");
    expect(tree[2]?.name).toBe(MEMORY_DIR);
    expect(tree[3]?.type).toBe("folder");
    expect(tree[3]?.name).toBe(MEDIA_DIR);
    const media = tree[3];
    if (media?.type !== "folder") throw new Error("expected media folder");
    const childNames = media.children.map((c) => c.name).sort();
    expect(childNames).toEqual(["上传", "生成"]);
    expect(tree.some((n) => n.name === "a")).toBe(true);
    const memory = tree[2];
    if (memory?.type !== "folder") throw new Error("expected memory folder");
    expect(memory.children).toEqual([]);
  });

  it("keeps media folder structure but omits media files from the tree", () => {
    const tree = buildFileTree([
      `${MEDIA_DIR}/生成/2026/logo.svg`,
      `${MEDIA_DIR}/上传/2026/shot.png`,
      "备忘/note.md",
    ]);
    const media = tree.find((n) => n.name === MEDIA_DIR);
    if (media?.type !== "folder") throw new Error("expected media folder");
    const gen = media.children.find((c) => c.name === "生成");
    if (gen?.type !== "folder") throw new Error("expected 生成");
    const year = gen.children.find((c) => c.name === "2026");
    if (year?.type !== "folder") throw new Error("expected year");
    expect(year.children).toEqual([]);
    const notes = tree.find((n) => n.name === "备忘");
    if (notes?.type !== "folder") throw new Error("expected 备忘");
    expect(notes.children.some((c) => c.type === "file")).toBe(true);
  });
});

describe("fileTreeFileIcon", () => {
  it("uses image icon for image paths, attach for other binaries, doc for md", () => {
    expect(fileTreeFileIcon("媒体/上传/2026/a.png")).toBe("🖼");
    expect(fileTreeFileIcon("notes/x.pdf")).toBe("📎");
    expect(fileTreeFileIcon("notes/x.md")).toBe("📄");
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
