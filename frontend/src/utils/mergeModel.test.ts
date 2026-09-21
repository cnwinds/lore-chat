import { describe, expect, it } from "vitest";
import {
  applyResultEdit,
  buildMergeBlocks,
  buildPaneRows,
  computePaneFillers,
  conflictSide,
  ignoreConflict,
  isUnresolved,
  resolveConflict,
  resultLayout,
  resultText,
  setSideState,
  toLines,
  withDocumentEnding,
  type ConflictBlock,
} from "./mergeModel";

describe("toLines", () => {
  it("keeps blank lines and drops the trailing-newline artifact", () => {
    expect(toLines("a\nb\n")).toEqual(["a", "b"]);
    expect(toLines("a\n\nb")).toEqual(["a", "", "b"]);
    expect(toLines("")).toEqual([]);
    expect(toLines("a")).toEqual(["a"]);
  });
});

describe("buildMergeBlocks", () => {
  it("returns one equal block when ours and theirs agree", () => {
    const blocks = buildMergeBlocks("a\nb\n", "a\nb\n", "a\nb\n");
    expect(blocks).toHaveLength(1);
    expect(blocks[0].kind).toBe("equal");
    expect(resultText(blocks)).toBe("a\nb");
  });

  it("auto-applies a change only ours made", () => {
    const blocks = buildMergeBlocks("a\nb\nc\n", "a\nX\nc\n", "a\nb\nc\n");
    expect(blocks).toHaveLength(3);
    expect(blocks[1].kind).toBe("side");
    if (blocks[1].kind !== "side") return;
    expect(blocks[1].side).toBe("ours");
    expect(blocks[1].state).toBe("applied");
    expect(resultText(blocks)).toBe("a\nX\nc");
  });

  it("auto-applies a change only theirs made", () => {
    const blocks = buildMergeBlocks("a\nb\nc\n", "a\nb\nc\n", "a\nY\nc\n");
    if (blocks[1].kind !== "side") throw new Error("expected side block");
    expect(blocks[1].side).toBe("theirs");
    expect(resultText(blocks)).toBe("a\nY\nc");
  });

  it("keeps a blank-line gap between two conflicts", () => {
    const base = "## 一\n甲。\n\n## 二\n乙。\n";
    const ours = "## 一\n甲改。\n\n## 二\n乙改。\n";
    const theirs = "## 一\n甲官。\n\n## 二\n乙官。\n";
    const blocks = buildMergeBlocks(base, ours, theirs);
    const conflicts = blocks.filter((b) => b.kind === "conflict");
    expect(conflicts).toHaveLength(2);
    // 中间的间隔（空行 + 「## 二」标题）equal 块不能被吞掉
    const gap = blocks[2];
    expect(gap.kind).toBe("equal");
    expect(gap.lines).toEqual(["", "## 二"]);
    expect(resultText(blocks)).toBe("## 一\n甲改。\n\n## 二\n乙改。");
  });

  it("marks identical changes on both sides as equal", () => {
    const blocks = buildMergeBlocks("a\nb\n", "a\nB\n", "a\nB\n");
    expect(blocks).toHaveLength(1);
    expect(blocks[0].kind).toBe("equal");
  });

  it("treats base==ours as cherry-pickable theirs chunks (history view)", () => {
    const blocks = buildMergeBlocks("a\nb\nc\n", "a\nb\nc\n", "a\nB2\nc\nC2\n");
    const sides = blocks.filter((b) => b.kind === "side");
    expect(sides).toHaveLength(2);
    expect(blocks.filter((b) => b.kind === "conflict")).toHaveLength(0);
    expect(resultText(blocks)).toBe("a\nB2\nc\nC2");
  });

  it("maps side ranges onto the untouched opposite pane", () => {
    const blocks = buildMergeBlocks("a\nb\nc\n", "a\nb\nc\n", "a\nY\nY2\nc\n");
    const side = blocks[1];
    if (side.kind !== "side") throw new Error("expected side block");
    expect(side.oursRange).toEqual({ start: 1, end: 2 });
    expect(side.theirsRange).toEqual({ start: 1, end: 3 });
  });
});

describe("resolutions", () => {
  const blocks = buildMergeBlocks(
    "head\n旧。\ntail\n",
    "head\n我改。\ntail\n",
    "head\n官改。\ntail\n",
  );
  const conflict = blocks[1];
  if (conflict.kind !== "conflict") throw new Error("expected conflict");

  it("starts pending with ours content", () => {
    expect(isUnresolved(conflict)).toBe(true);
    expect(conflict.lines).toEqual(["我改。"]);
    expect(conflictSide(conflict)).toBeNull();
  });

  it("picks either side or both", () => {
    expect(resolveConflict(conflict, "theirs").lines).toEqual(["官改。"]);
    expect(conflictSide(resolveConflict(conflict, "theirs"))).toBe("theirs");
    expect(resolveConflict(conflict, "ours").lines).toEqual(["我改。"]);
    expect(resolveConflict(conflict, "both").lines).toEqual(["我改。", "官改。"]);
    expect(isUnresolved(resolveConflict(conflict, "theirs"))).toBe(false);
  });

  it("ignoring keeps the current lines but resolves", () => {
    const ignored = ignoreConflict(conflict);
    expect(isUnresolved(ignored)).toBe(false);
    expect(ignored.lines).toEqual(["我改。"]);
  });

  it("ignoring a side chunk falls back to base lines", () => {
    const only = buildMergeBlocks("a\nb\nc\n", "a\nb\nc\n", "a\nY\nc\n");
    const side = only[1];
    if (side.kind !== "side") throw new Error("expected side block");
    expect(resultText([side])).toBe("Y");
    expect(resultText([setSideState(side, "ignored")])).toBe("b");
  });
});

describe("applyResultEdit", () => {
  const blocks = buildMergeBlocks(
    "h\n旧。\ntail\n",
    "h\n我改。\ntail\n",
    "h\n官改。\ntail\n",
  );
  const layout = resultLayout(blocks);

  function edit(blockIndexToReplace: number, nextLines: string[]) {
    const merged = [...layout.lines];
    merged.splice(
      layout.blockStart[blockIndexToReplace],
      blocks[blockIndexToReplace].lines.length,
      ...nextLines,
    );
    return applyResultEdit(blocks, layout, merged);
  }

  it("turns the edited chunk into one custom block", () => {
    const next = edit(1, ["手改。"]);
    expect(next).toHaveLength(3);
    expect(next[1].kind).toBe("custom");
    expect(next[1].lines).toEqual(["手改。"]);
    expect(resultText(next)).toBe("h\n手改。\ntail");
  });

  it("keeps an insertion at a block boundary", () => {
    const merged = ["h", "新行。", "我改。", "tail"];
    const next = applyResultEdit(blocks, layout, merged);
    expect(resultText(next)).toBe("h\n新行。\n我改。\ntail");
    expect(next.filter((b) => b.kind === "custom")).toHaveLength(1);
  });

  it("handles the first edit on an empty result", () => {
    const empty = buildMergeBlocks("", "", "");
    const next = applyResultEdit(
      empty,
      resultLayout(empty),
      "第一行".split("\n"),
    );
    expect(resultText(next)).toBe("第一行");
  });
});

describe("resultLayout", () => {
  it("maps every result line to its block", () => {
    const blocks = buildMergeBlocks(
      "a\nb\nc\n",
      "a\nX\nc\n",
      "a\nb\nc\n",
    );
    const layout = resultLayout(blocks);
    expect(layout.lines).toEqual(["a", "X", "c"]);
    expect(layout.lineBlock).toEqual([0, 1, 2]);
    expect(layout.blockStart).toEqual([0, 1, 2]);
  });
});

describe("withDocumentEnding", () => {
  it("keeps the reference ending", () => {
    expect(withDocumentEnding("a\nb", "x\ny\n")).toBe("a\nb\n");
    expect(withDocumentEnding("a\nb\n", "x\ny")).toBe("a\nb");
    expect(withDocumentEnding("", "x\n")).toBe("");
  });
});

describe("戒律更新 fixture", () => {
  const ours = "# 戒律\n\n## 八、目录规划\n受保护区域。\n\n## 九、无痕教学（陪伴学习）\n建构优先。\n\n## 附录\n只在现行。\n";
  const theirs = "# 戒律\n\n## 七、目录规划\n受保护区域。\n\n## 八、用户生成 Skill\n新建 Skill 包仅当用户明确要求。\n";
  const base = "# 戒律\n\n## 八、目录规划\n受保护区域。\n";

  function firstConflict(blocks: ReturnType<typeof buildMergeBlocks>) {
    return blocks.find((b): b is ConflictBlock => b.kind === "conflict");
  }

  it("default result keeps ours and can flip one conflict to theirs", () => {
    const blocks = buildMergeBlocks(base, ours, theirs);
    const conflict = firstConflict(blocks);
    expect(conflict).toBeDefined();
    expect(resultText(blocks)).toContain("无痕教学");
    const picked = blocks.map((b) =>
      b === conflict ? resolveConflict(conflict!, "theirs") : b,
    );
    const body = withDocumentEnding(resultText(picked), theirs);
    expect(body).toContain("用户生成 Skill");
    expect(body).not.toContain("无痕教学");
    // 标准三路语义：两侧在同一位置各加了不同小节，选官方就整个换成官方侧
    expect(body).not.toContain("附录");
    expect(body.endsWith("\n")).toBe(true);
    const bothBody = withDocumentEnding(
      resultText(
        blocks.map((b) => (b === conflict ? resolveConflict(conflict!, "both") : b)),
      ),
      theirs,
    );
    expect(bothBody).toContain("用户生成 Skill");
    expect(bothBody).toContain("无痕教学");
    expect(bothBody).toContain("附录");
  });

  it("写完仍可用官方（整篇含结尾换行）", () => {
    const blocks = buildMergeBlocks(base, ours, theirs);
    const conflict = firstConflict(blocks)!;
    const picked = blocks.map((b) =>
      b.id === conflict.id ? resolveConflict(conflict, "theirs") : b,
    );
    const body = withDocumentEnding(resultText(picked), theirs);
    expect(body).toContain("## 七、目录规划");
    expect(body.split("\n").length).toBeGreaterThan(5);
  });
});

describe("computePaneFillers / buildPaneRows", () => {
  // theirs 在文首比 ours 多 2 行 → 插 2 行填充后两栏的块起始对齐
  const ours = ["# 标题", "", "正文第一段。"].join("\n");
  const theirs = [
    "# 标题",
    "",
    "开头引言。",
    "开头引言二。",
    "正文第一段。",
  ].join("\n");
  const blocks = buildMergeBlocks(ours, ours, theirs);

  it("在较短的栏补齐填充行（文末对齐）", () => {
    const fillers = computePaneFillers(blocks);
    // 差异在文档尾部：块前无需填充，文末 ours 补 2 行对齐
    expect(fillers.end.ours).toBe(2);
    expect(fillers.end.theirs).toBe(0);
  });

  it("buildPaneRows 输出含填充行且正文行数与栏内容一致", () => {
    const fillers = computePaneFillers(blocks);
    const oursRows = buildPaneRows("ours", blocks, fillers);
    const theirsRows = buildPaneRows("theirs", blocks, fillers);
    const fillerRows = oursRows.filter((r) => r.kind === "filler").length;
    expect(fillerRows).toBe(2);
    expect(oursRows).toHaveLength(theirsRows.length);
    expect(oursRows.some((r) => r.kind === "line" && r.text === "正文第一段。")).toBe(true);
    // 相同行不得被标成 custom（回归：equal 落空曾全标金）
    const resultRows = buildPaneRows("result", blocks, fillers);
    expect(resultRows.some((r) => r.kind === "line" && r.tone === "custom")).toBe(false);
  });
});
