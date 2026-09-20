import { describe, expect, it } from "vitest";
import { merge3Regions } from "./textMerge3";
import {
  assembleMergeDraft,
  assembleMergeSegments,
  buildMergeView,
  defaultHunkPick,
} from "./preceptsMergeView";

describe("merge3Regions", () => {
  it("keeps independent official wording as its own hunk", () => {
    const base = "# 戒律\n旧句。\n## 目录\n保护。\n";
    const ours = "# 戒律\n旧句。\n## 目录\n保护。\n## 九、无痕教学\n本地。\n";
    const theirs = "# 戒律\n新句。\n## 目录\n保护。\n## 八、Skill\n官方。\n";
    const regions = merge3Regions(base, ours, theirs);
    const hunks = regions.filter((r) => r.type === "change").map((r) => r.hunk);
    expect(hunks.some((hunk) => hunk.theirs.includes("新句") && hunk.kind === "theirs")).toBe(
      true,
    );
    const draft = assembleMergeDraft(regions);
    expect(draft).toContain("新句");
    expect(draft).toContain("无痕教学");
    expect(draft).toContain("Skill");
  });

  it("merges official edits inside a renamed 目录规划 section", () => {
    const ours = `# 戒律

## 八、目录规划（知识库归类）
受保护区域：见第七节。

## 九、无痕教学（陪伴学习）
建构优先。

## 附录
只在现行。
`;
    const theirs = `# 戒律

## 七、目录规划（知识库归类）
受保护区域：见第六节。

## 八、用户生成 Skill
新建 Skill 包仅当用户明确要求。
`;
    const base = `# 戒律

## 八、目录规划（知识库归类）
受保护区域：见第七节。
`;
    const view = buildMergeView(base, ours, theirs);
    expect(
      view.hunks.some(
        (hunk) => hunk.kind === "theirs" && hunk.theirs.includes("七、目录规划"),
      ),
    ).toBe(true);
    expect(
      view.hunks.some(
        (hunk) => hunk.kind === "theirs" && hunk.theirs.includes("见第六节"),
      ),
    ).toBe(true);
    expect(view.hunks.some((hunk) => hunk.kind === "ours" && hunk.ours.includes("附录"))).toBe(
      true,
    );
    const draft = assembleMergeDraft(view.regions);
    expect(draft).toContain("## 七、目录规划（知识库归类）");
    expect(draft).toContain("见第六节");
    expect(draft).not.toContain("## 八、目录规划");
    expect(draft).not.toContain("见第七节");
    expect(draft).toContain("无痕教学");
    expect(draft).toContain("用户生成 Skill");
    expect(draft).toContain("附录");
    const painted = assembleMergeSegments(view.regions);
    expect(
      painted.some(
        (segment) =>
          segment.origin === "theirs" && segment.text.includes("七、目录规划"),
      ),
    ).toBe(true);
    expect(
      painted.some(
        (segment) => segment.origin === "theirs" && segment.text.includes("见第六节"),
      ),
    ).toBe(true);
    expect(
      painted.some((segment) => segment.origin === "ours" && segment.text.includes("无痕教学")),
    ).toBe(true);

    const picks = view.hunks.map((hunk) =>
      hunk.ours.includes("无痕教学") ? "theirs" : defaultHunkPick(hunk),
    );
    const afterDropLocal = assembleMergeDraft(view.regions, picks);
    expect(afterDropLocal).not.toContain("无痕教学");
    expect(afterDropLocal).toContain("附录");
    expect(afterDropLocal).toContain("## 七、目录规划");
  });

  it("only marks changed lines inside a section, not the unchanged body", () => {
    const body = `1. 先看清结构。
2. 归类决策。
`;
    const base = `# 戒律\n## 八、目录规划\n${body}5. 受保护区域：见第七节。\n`;
    const ours = base;
    const theirs = `# 戒律\n## 七、目录规划\n${body}5. 受保护区域：见第六节。\n`;
    const view = buildMergeView(base, ours, theirs);
    const draft = assembleMergeDraft(view.regions);
    expect(draft).toContain("## 七、目录规划");
    expect(draft).toContain("先看清结构");
    expect(draft).toContain("见第六节");
    expect(draft).not.toContain("## 八、目录规划");
    const paintedOfficial = assembleMergeSegments(view.regions)
      .filter((segment) => segment.origin === "theirs")
      .map((segment) => segment.text)
      .join("");
    expect(paintedOfficial).toContain("七、目录规划");
    expect(paintedOfficial).toContain("见第六节");
    expect(paintedOfficial).not.toContain("先看清结构");
    expect(paintedOfficial).not.toContain("归类决策");
    const officialRangeLines = view.hunks.flatMap((hunk) => {
      if (!hunk.theirsRange) return [];
      return theirs.split("\n").slice(hunk.theirsRange.start, hunk.theirsRange.end);
    });
    expect(officialRangeLines.some((line) => line.includes("七、目录规划"))).toBe(true);
    expect(officialRangeLines.some((line) => line.includes("见第六节"))).toBe(true);
    expect(officialRangeLines.some((line) => line.includes("先看清结构"))).toBe(false);
  });
});
