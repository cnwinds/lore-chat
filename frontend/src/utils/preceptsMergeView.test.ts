import { describe, expect, it } from "vitest";
import {
  assembleMergeDraft,
  applyHunkPick,
  buildMergeView,
  changeCounts,
  combineHunk,
  exclusiveHeadings,
  foldUnchanged,
  hunkTitle,
  initialMergeDraft,
  firstEdit,
  hunkIndexAtLine,
  lineRange,
  locateHunkSpans,
  replaceSpan,
  shiftSpans,
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
      base: "# 戒律\n5. **受保护区域**：见第七节。\n",
      ours: "# 戒律\n" + OURS,
      theirs: "# 戒律\n" + THEIRS,
      proposed: "# 戒律\n" + OURS,
      conflicts: [{ base: "5. **受保护区域**：见第七节。\n", ours: OURS, theirs: THEIRS }],
    });
    expect(draft).toContain("无痕教学");
    expect(draft).toContain("用户生成 Skill");
  });

  it("keeps auto-merged official text and highlights it", () => {
    const base = "# 戒律\n旧句。\n## 目录\n保护。\n";
    const ours = "# 戒律\n旧句。\n## 目录\n保护。\n## 九、无痕教学\n本地。\n";
    const theirs = "# 戒律\n新句。\n## 目录\n保护。\n## 八、Skill\n官方。\n";
    const view = buildMergeView(base, ours, theirs);
    expect(view.hunks.some((hunk) => hunk.theirs.includes("新句"))).toBe(true);
    expect(
      view.hunks.some((hunk) => hunk.theirsRange != null && hunk.theirs.includes("新句")),
    ).toBe(true);
    const draft = assembleMergeDraft(view.regions);
    expect(draft).toContain("新句");
    expect(draft).toContain("无痕教学");
    expect(draft).toContain("Skill");
  });

  it("taking the right side of every hunk yields the official document", () => {
    const ours = "# 戒律\n本地A\n本地B\n尾\n";
    const theirs = "# 戒律\n官方A\n官方B\n官方C\n尾\n";
    const view = buildMergeView("", ours, theirs);
    const picks = view.hunks.map(() => "theirs" as const);
    expect(assembleMergeDraft(view.regions, picks)).toBe(theirs);
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

  it("maps a conflict snippet to document lines", () => {
    const range = lineRange(
      "# 戒律\n## 九、无痕教学（陪伴学习）\n建构优先。\n尾\n",
      "## 九、无痕教学（陪伴学习）\n建构优先。\n",
    );
    expect(range).toEqual({ start: 1, end: 3 });
    expect(hunkIndexAtLine([range], 0)).toBe(-1);
    expect(hunkIndexAtLine([range], 1)).toBe(0);
    expect(hunkIndexAtLine([range], 2)).toBe(0);
    expect(hunkIndexAtLine([range], 3)).toBe(-1);
  });

  it("keeps a hunk span through an edit so a later pick still replaces it", () => {
    const both = combineHunk(OURS, THEIRS);
    const draft = `# 戒律\n${both}尾\n`;
    const spans = locateHunkSpans(draft, [both]);
    expect(spans[0]).not.toBeNull();
    const nextDraft = draft.replace("建构优先。", "建构优先。改。");
    const edit = firstEdit(draft, nextDraft);
    expect(edit).not.toBeNull();
    const moved = shiftSpans(spans, edit!.at, edit!.oldLen, edit!.newLen);
    const replaced = replaceSpan(nextDraft, moved[0]!, THEIRS);
    expect(replaced).toContain("用户生成 Skill");
    expect(replaced).not.toContain("无痕教学");
    expect(replaced).toContain("尾");
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
