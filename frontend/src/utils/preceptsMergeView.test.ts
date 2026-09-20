import { describe, expect, it } from "vitest";
import {
  applyHunkPick,
  changeCounts,
  combineHunk,
  exclusiveHeadings,
  foldUnchanged,
  hunkTitle,
  initialMergeDraft,
  type ConflictSides,
} from "./preceptsMergeView";

const OURS = `5. **受保护区域**：见第七节。

## 九、无痕教学（陪伴学习）
建构优先。
`;
const THEIRS = `5. **受保护区域**：见第六节。

## 八、用户生成 Skill
新建 Skill 包仅当用户明确要求。
`;

describe("preceptsMergeView", () => {
  it("names a conflict from both headings", () => {
    expect(
      hunkTitle({
        base: "5. 受保护区域\n",
        ours: OURS,
        theirs: THEIRS,
      }),
    ).toBe("无痕教学（陪伴学习） · 用户生成 Skill");
  });

  it("keeps both sides of a git-style hunk", () => {
    const combined = combineHunk(OURS, THEIRS);
    expect(combined).toContain("无痕教学");
    expect(combined).toContain("用户生成 Skill");
  });

  it("builds a draft that keeps local and official additions", () => {
    const draft = initialMergeDraft({
      ours: "# 戒律\n" + OURS,
      proposed: "# 戒律\n" + OURS,
      conflicts: [{ base: "5. **受保护区域**：见第七节。\n", ours: OURS, theirs: THEIRS }],
    });
    expect(draft).toContain("无痕教学");
    expect(draft).toContain("用户生成 Skill");
  });

  it("keeps auto-merged official text outside the conflict", () => {
    const draft = initialMergeDraft({
      base: "# 戒律\n",
      ours: `# 戒律\n${OURS}`,
      theirs: `# 戒律\n官方独有段\n${THEIRS}`,
      proposed: `# 戒律\n官方独有段\n${OURS}`,
      conflicts: [{ base: "", ours: OURS, theirs: THEIRS }],
    });
    expect(draft).toContain("无痕教学");
    expect(draft).toContain("用户生成 Skill");
    expect(draft).toContain("官方独有段");
  });

  it("does not replace the whole draft when the hunk is gone", () => {
    const hunk: ConflictSides = { base: "", ours: OURS, theirs: THEIRS };
    const kept = applyHunkPick("# 戒律\n附录\n", hunk, "not-in-draft", "theirs");
    expect(kept).toContain("附录");
    expect(kept).not.toContain("用户生成 Skill");
  });

  it("switches a hunk among ours, theirs, and both", () => {
    const hunk: ConflictSides = { base: "", ours: OURS, theirs: THEIRS };
    const both = combineHunk(OURS, THEIRS);
    const afterOfficial = applyHunkPick(both, hunk, both, "theirs");
    expect(afterOfficial).toContain("用户生成 Skill");
    expect(afterOfficial).not.toContain("无痕教学");
    const afterBoth = applyHunkPick(afterOfficial, hunk, THEIRS, "both");
    expect(afterBoth).toContain("无痕教学");
    expect(afterBoth).toContain("用户生成 Skill");
  });

  it("counts added and removed lines", () => {
    expect(
      changeCounts([
        { type: "unchanged", content: "keep" },
        { type: "removed", content: "old" },
        { type: "added", content: "new" },
        { type: "added", content: "more" },
      ]),
    ).toEqual({ plus: 2, minus: 1 });
  });

  it("lists headings that did not overlap", () => {
    const extra = exclusiveHeadings(
      "# 戒律\n## 目录规划\n",
      "# 戒律\n## 目录规划\n## 附录\n只在现行。\n" + OURS,
      "# 戒律\n## 目录规划\n" + THEIRS,
      [{ base: "", ours: OURS, theirs: THEIRS }],
    );
    expect(extra.ours).toEqual(["附录"]);
    expect(extra.theirs).toEqual([]);
  });

  it("folds a long unchanged run", () => {
    const lines = [
      ...Array.from({ length: 12 }, () => ({
        type: "unchanged" as const,
        content: "same",
      })),
      { type: "added" as const, content: "new" },
    ];
    const folded = foldUnchanged(lines, 2, 6);
    expect(folded.some((row) => row.kind === "fold")).toBe(true);
  });
});
