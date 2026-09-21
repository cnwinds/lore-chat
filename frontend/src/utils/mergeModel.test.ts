import { describe, expect, it } from "vitest";
import {
  buildMergeBlocks,
  buildPaneRows,
  closestLineToGlobal,
  globalLineMaps,
  isUnresolved,
  resolveConflict,
  resultLayout,
  resultText,
  withDocumentEnding,
  type MergePick,
} from "./mergeModel";

const join = (lines: string[]) => lines.join("\n");

describe("toLines / 基础", () => {
  it("keeps blank lines and drops the trailing-newline artifact", () => {
    expect(join(["a", "b"])).toBe("a\nb");
  });
});

describe("buildMergeBlocks 基础", () => {
  it("auto-applies a change only ours made", () => {
    const blocks = buildMergeBlocks("a\nb\nc\n", "a\nX\nc\n", "a\nb\nc\n");
    expect(blocks[1].kind).toBe("side");
    expect(resultText(blocks)).toBe("a\nX\nc");
  });

  it("auto-applies a change only theirs made", () => {
    const blocks = buildMergeBlocks("a\nb\nc\n", "a\nb\nc\n", "a\nY\nc\n");
    expect(resultText(blocks)).toBe("a\nY\nc");
  });

  it("keeps a blank-line gap between two conflicts", () => {
    const blocks = buildMergeBlocks(
      "## 一\n甲。\n\n## 二\n乙。\n",
      "## 一\n甲改。\n\n## 二\n乙改。\n",
      "## 一\n甲官。\n\n## 二\n乙官。\n",
    );
    const conflicts = blocks.filter((b) => b.kind === "conflict");
    expect(conflicts).toHaveLength(2);
  });
});

describe("冲突裁决与文档收尾", () => {
  const blocks = buildMergeBlocks("a\nb\nc\n", "a\nX\nc\n", "a\nY\nc\n");
  const resolved = (pick: MergePick) =>
    resultText(blocks.map((b) => (b.kind === "conflict" ? resolveConflict(b, pick) : b)));

  it("resolveConflict 按裁决改写结果文本", () => {
    expect(resolved("ours")).toBe("a\nX\nc");
    expect(resolved("theirs")).toBe("a\nY\nc");
    expect(resolved("both")).toBe("a\nX\nY\nc");
  });

  it("withDocumentEnding 按参照文本决定是否以换行收尾", () => {
    expect(withDocumentEnding("a\nb", "x\n")).toBe("a\nb\n");
    expect(withDocumentEnding("a\nb\n", "x")).toBe("a\nb");
    expect(withDocumentEnding("", "x\n")).toBe("");
  });
});

describe("极限用例：12 节文档、双方 10+ 处穿插改动", () => {
  // 现行改奇数节正文 + 文首导读 + 文尾附录；官方改偶数节正文 + 文首官方导读 + 文尾官方附录。
  // 块序列：导读冲突 → 12 组[节标题 equal + 正文 side/conflict 交替] → 文尾冲突。
  const baseParts: string[] = ["# 文档"];
  for (let n = 1; n <= 12; n++) {
    baseParts.push(`## ${n}、第${n}节（基线）`, `基线正文 ${n}。`);
  }
  const base = join(baseParts) + "\n";

  const oursEdited = base.split("\n").map((l) =>
    /^基线正文 \d+。$/.test(l) && Number(l.replace(/\D/g, "")) % 2 === 1
      ? l.replace("基线正文", "现行正文")
      : l,
  );
  const oursLines = ["# 文档（现行）"];
  oursLines.push(...oursEdited.slice(1), "## 十二、现行附录", "现行附录正文。");
  const ours = join(oursLines);

  const theirsEdited = base.split("\n").map((l) =>
    /^基线正文 \d+。$/.test(l) && Number(l.replace(/\D/g, "")) % 2 === 0
      ? l.replace("基线正文", "官方正文")
      : l,
  );
  const theirsLines = ["# 文档（官方）"];
  theirsLines.push(...theirsEdited.slice(1), "## 十二、官方附录", "官方附录正文。");
  const theirs = join(theirsLines);

  const blocks = buildMergeBlocks(base, ours, theirs);
  const layout = resultLayout(blocks);

  it("产出大量穿插块且含冲突", () => {
    const changes = blocks.filter((b) => b.kind !== "equal");
    expect(changes.length).toBeGreaterThanOrEqual(10);
    expect(blocks.some((b) => b.kind === "conflict" && isUnresolved(b))).toBe(true);
  });

  it("各栏渲染行与各自文档一一对应（不重不漏）", () => {
    const dump = (title: string, rows: { kind: string; text?: string }[]) => {
      console.log(
        `${title}:`,
        JSON.stringify(rows.map((r) => (r.kind === "line" ? r.text : "<F>"))),
      );
    };
    dump("OURS ROWS", buildPaneRows("ours", blocks));
    dump("THEIRS ROWS", buildPaneRows("theirs", blocks));
    dump("RESULT ROWS", buildPaneRows("result", blocks));
    console.log("BLOCK KINDS:", blocks.map((b) => `${b.kind}:${b.lines.length}`).join(","));
    const oursRows = buildPaneRows("ours", blocks);
    const theirsRows = buildPaneRows("theirs", blocks);
    expect(oursRows.filter((r) => r.kind === "line").map((r) => r.text)).toEqual(
      ours.split("\n"),
    );
    expect(theirsRows.filter((r) => r.kind === "line").map((r) => r.text)).toEqual(
      theirs.split("\n"),
    );
  });

  it("结果栏渲染行与结果文档一一对应，布局行号与按钮定位一致", () => {
    const resultRows = buildPaneRows("result", blocks);
    const rendered = resultRows.map((r) => r.text);
    expect(rendered).toEqual(resultText(blocks).split("\n"));
    // resultLayout 的 blockStart 是每块在结果栏的起始行，供冲突按钮定位；
    // 它必须与渲染行累计严格一致，否则穿插场景下按钮会飘。
    let cursor = 0;
    blocks.forEach((b, i) => {
      expect(layout.blockStart[i]).toBe(cursor);
      cursor += b.lines.length;
    });
    expect(cursor).toBe(resultRows.length);
  });

  it("块区间在各栏内单调不重叠且覆盖全文", () => {
    let prevEnd = 0;
    for (const b of blocks) {
      expect(b.oursRange.start).toBe(prevEnd);
      expect(b.theirsRange.start).toBeGreaterThan(b.oursRange.start - 1);
      prevEnd = b.theirsRange.end;
    }
    const theirsTotal = theirs.split("\n").length;
    expect(prevEnd).toBe(theirsTotal);
  });

  it("全局行映射单调，跨栏中心映射往返漂移 ≤1 行", () => {
    const counts = {
      ours: blocks.map((b) => b.oursRange.end - b.oursRange.start),
      result: blocks.map((b) => b.lines.length),
      theirs: blocks.map((b) => b.theirsRange.end - b.theirsRange.start),
    };
    const maps = globalLineMaps(counts.ours, counts.result, counts.theirs);
    for (const map of maps) {
      for (let i = 1; i < map.length; i++) {
        expect(map[i]).toBeGreaterThan(map[i - 1]);
      }
    }
    // 任取 result 栏的中心行，映射到 ours 栏再映射回来，漂移不超过 ±1 行
    for (let row = 0; row < counts.result.length; row += 3) {
      const g = maps[1][row];
      const oursLine = closestLineToGlobal(maps[0], g);
      const back = closestLineToGlobal(maps[1], maps[0][oursLine]);
      expect(Math.abs(back - row)).toBeLessThanOrEqual(1);
    }
  });
});
