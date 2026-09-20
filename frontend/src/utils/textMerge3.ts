import { diffArrays } from "diff";

export type ChangeKind = "ours" | "theirs" | "conflict";

export type Merge3Hunk = {
  kind: ChangeKind;
  base: string;
  ours: string;
  theirs: string;
};

export type Merge3Region =
  | { type: "equal"; text: string }
  | { type: "change"; hunk: Merge3Hunk };

type Opcode = {
  tag: "equal" | "delete" | "insert" | "replace";
  i1: number;
  i2: number;
  j1: number;
  j2: number;
};

type Cluster = {
  i1: number;
  i2: number;
  oursChanged: boolean;
  theirsChanged: boolean;
};

function splitKeep(text: string): string[] {
  if (text === "") return [];
  const parts = text.split("\n");
  const last = parts.pop() ?? "";
  const lines = parts.map((part) => `${part}\n`);
  if (last !== "") lines.push(last);
  return lines;
}

function join(lines: string[]): string {
  return lines.join("");
}

function opcodes(a: string[], b: string[]): Opcode[] {
  const changes = diffArrays(a, b);
  let i = 0;
  let j = 0;
  const raw: Opcode[] = [];
  for (const change of changes) {
    const n = change.value.length;
    if (change.added) {
      raw.push({ tag: "insert", i1: i, i2: i, j1: j, j2: j + n });
      j += n;
    } else if (change.removed) {
      raw.push({ tag: "delete", i1: i, i2: i + n, j1: j, j2: j });
      i += n;
    } else {
      raw.push({ tag: "equal", i1: i, i2: i + n, j1: j, j2: j + n });
      i += n;
      j += n;
    }
  }
  const out: Opcode[] = [];
  for (const op of raw) {
    const prev = out[out.length - 1];
    if (
      prev &&
      prev.tag === "delete" &&
      op.tag === "insert" &&
      prev.i2 === op.i1 &&
      prev.j2 === op.j1
    ) {
      out[out.length - 1] = {
        tag: "replace",
        i1: prev.i1,
        i2: prev.i2,
        j1: op.j1,
        j2: op.j2,
      };
      continue;
    }
    out.push(op);
  }
  return out;
}

function splitMarkdown(text: string): string[] {
  const lines = splitKeep(text);
  if (!lines.length) return [];
  const sections: string[] = [];
  let cur: string[] = [];
  for (const line of lines) {
    if (/^#{1,3}\s+/.test(line) && cur.length) {
      sections.push(join(cur));
      cur = [];
    }
    cur.push(line);
  }
  if (cur.length) sections.push(join(cur));
  return sections;
}

function sectionKey(section: string): string {
  const line = splitKeep(section).find((item) => /^#{1,3}\s+/.test(item)) || "";
  return line.replace(/^#{1,6}\s+/, "").replace(/^[一二三四五六七八九十]+、/, "").trim();
}

function hasHeading(sections: string[]): boolean {
  return sections.some((section) => /^#{1,3}\s+/m.test(section));
}

function indexSections(sections: string[]): Map<string, string[]> {
  const map = new Map<string, string[]>();
  for (const section of sections) {
    const key = sectionKey(section);
    const list = map.get(key) ?? [];
    list.push(section);
    map.set(key, list);
  }
  return map;
}

function takeBase(index: Map<string, string[]>, key: string): string {
  const list = index.get(key);
  if (!list?.length) return "";
  return list.shift() ?? "";
}

function overlap(a1: number, a2: number, b1: number, b2: number): boolean {
  if (a1 === a2 && b1 === b2) return a1 === b1;
  // 半开区间：落在上一处改动末尾的空行插入，不算和这一处重叠。
  if (a1 === a2) return b1 <= a1 && a1 < b2;
  if (b1 === b2) return a1 <= b1 && b1 < a2;
  return a1 < b2 && b1 < a2;
}

/** 节末用来隔开下一节的空行，不参与「改没改」的判断。 */
function trailNorm(text: string): string {
  if (!text) return text;
  return text.replace(/(?:[ \t]*\n)+$/, "\n");
}

function nonEqual(base: string[], side: string[]): Opcode[] {
  return opcodes(base, side).filter((op) => op.tag !== "equal");
}

function clusters(oursEdits: Opcode[], theirsEdits: Opcode[]): Cluster[] {
  const items: Array<{ side: "ours" | "theirs"; i1: number; i2: number }> = [];
  for (const edit of oursEdits) items.push({ side: "ours", i1: edit.i1, i2: edit.i2 });
  for (const edit of theirsEdits) {
    items.push({ side: "theirs", i1: edit.i1, i2: edit.i2 });
  }
  items.sort((a, b) => a.i1 - b.i1 || a.i2 - b.i2 || a.side.localeCompare(b.side));
  if (!items.length) return [];
  const groups: Cluster[] = [];
  let cur: Cluster = {
    i1: items[0]!.i1,
    i2: items[0]!.i2,
    oursChanged: items[0]!.side === "ours",
    theirsChanged: items[0]!.side === "theirs",
  };
  for (const item of items.slice(1)) {
    if (overlap(cur.i1, cur.i2, item.i1, item.i2)) {
      cur.i1 = Math.min(cur.i1, item.i1);
      cur.i2 = Math.max(cur.i2, item.i2);
      cur.oursChanged = cur.oursChanged || item.side === "ours";
      cur.theirsChanged = cur.theirsChanged || item.side === "theirs";
      continue;
    }
    groups.push(cur);
    cur = {
      i1: item.i1,
      i2: item.i2,
      oursChanged: item.side === "ours",
      theirsChanged: item.side === "theirs",
    };
  }
  groups.push(cur);
  return groups;
}

function sideSpan(
  base: string[],
  side: string[],
  blo: number,
  bhi: number,
): string[] {
  const lines: string[] = [];
  const zero = blo === bhi;
  for (const op of opcodes(base, side)) {
    if (op.tag === "equal") {
      const olo = Math.max(op.i1, blo);
      const ohi = Math.min(op.i2, bhi);
      if (olo < ohi) {
        const off = op.j1 + (olo - op.i1);
        lines.push(...side.slice(off, off + (ohi - olo)));
      }
      continue;
    }
    if (op.tag === "delete") continue;
    if (op.tag === "insert") {
      if (op.i1 < blo || op.i1 > bhi) continue;
      if (op.i1 === bhi && !zero) continue;
      lines.push(...side.slice(op.j1, op.j2));
      continue;
    }
    const olo = Math.max(op.i1, blo);
    const ohi = Math.min(op.i2, bhi);
    if (olo < ohi) lines.push(...side.slice(op.j1, op.j2));
  }
  return lines;
}

function change(
  kind: ChangeKind,
  base: string,
  ours: string,
  theirs: string,
): Merge3Region {
  return { type: "change", hunk: { kind, base, ours, theirs } };
}

function isNumberingHeading(oursChunk: string, theirsChunk: string): boolean {
  const oursLine = splitKeep(oursChunk).find((line) => /^#{1,3}\s+/.test(line));
  const theirsLine = splitKeep(theirsChunk).find((line) => /^#{1,3}\s+/.test(line));
  if (!oursLine || !theirsLine) return false;
  const oursBody = oursChunk.replace(oursLine, "");
  const theirsBody = theirsChunk.replace(theirsLine, "");
  return sectionKey(oursLine) === sectionKey(theirsLine) && oursBody === theirsBody;
}

function twoWayLines(ours: string, theirs: string): Merge3Region[] {
  if (ours === theirs) return ours ? [{ type: "equal", text: ours }] : [];
  if (!ours.trim()) {
    return theirs ? [change("theirs", "", "", theirs)] : [];
  }
  if (!theirs.trim()) {
    return ours ? [change("ours", "", ours, "")] : [];
  }
  const left = splitKeep(ours);
  const right = splitKeep(theirs);
  const regions: Merge3Region[] = [];
  for (const op of opcodes(left, right)) {
    if (op.tag === "equal") {
      regions.push({ type: "equal", text: join(left.slice(op.i1, op.i2)) });
      continue;
    }
    if (op.tag === "delete") {
      regions.push(change("ours", "", join(left.slice(op.i1, op.i2)), ""));
      continue;
    }
    if (op.tag === "insert") {
      regions.push(change("theirs", "", "", join(right.slice(op.j1, op.j2))));
      continue;
    }
    const oursText = join(left.slice(op.i1, op.i2));
    const theirsText = join(right.slice(op.j1, op.j2));
    const kind = isNumberingHeading(oursText, theirsText) ? "theirs" : "conflict";
    regions.push(change(kind, "", oursText, theirsText));
  }
  return coalesce(regions);
}

function merge3Lines(base: string, ours: string, theirs: string): Merge3Region[] {
  if (ours === theirs) return ours ? [{ type: "equal", text: ours }] : [];
  if (!base.trim()) return twoWayLines(ours, theirs);
  if (!ours.trim()) {
    return theirs ? [change("theirs", base, "", theirs)] : [];
  }
  if (!theirs.trim()) {
    return ours ? [change("ours", base, ours, "")] : [];
  }
  const oursCore = trailNorm(ours);
  const theirsCore = trailNorm(theirs);
  if (oursCore === theirsCore) {
    return oursCore ? [{ type: "equal", text: ours }] : [];
  }

  const b = splitKeep(base);
  const o = splitKeep(ours);
  const t = splitKeep(theirs);
  const groups = clusters(nonEqual(b, o), nonEqual(b, t));
  if (!groups.length) {
    return ours ? [{ type: "equal", text: ours }] : [];
  }
  const regions: Merge3Region[] = [];
  let cursor = 0;
  for (const group of groups) {
    if (cursor < group.i1) {
      regions.push({ type: "equal", text: join(b.slice(cursor, group.i1)) });
    }
    const oursText = join(sideSpan(b, o, group.i1, group.i2));
    const theirsText = join(sideSpan(b, t, group.i1, group.i2));
    const baseText = join(b.slice(group.i1, group.i2));
    if (group.oursChanged && !group.theirsChanged) {
      regions.push(change("ours", baseText, oursText, theirsText));
    } else if (group.theirsChanged && !group.oursChanged) {
      regions.push(change("theirs", baseText, oursText, theirsText));
    } else if (oursText === theirsText) {
      if (oursText) regions.push({ type: "equal", text: oursText });
    } else {
      // 同一处两边都动了：再按行 diff，拆开只改一边的行
      regions.push(...twoWayLines(oursText, theirsText));
    }
    cursor = group.i2;
  }
  if (cursor < b.length) {
    regions.push({ type: "equal", text: join(b.slice(cursor)) });
  }
  return coalesce(regions);
}

function coalesce(regions: Merge3Region[]): Merge3Region[] {
  const out: Merge3Region[] = [];
  for (const region of regions) {
    if (region.type === "equal" && !region.text) continue;
    const prev = out[out.length - 1];
    if (region.type === "equal" && prev?.type === "equal") {
      out[out.length - 1] = { type: "equal", text: prev.text + region.text };
      continue;
    }
    out.push(region);
  }
  return out;
}

function mergeSections(base: string, ours: string, theirs: string): Merge3Region[] {
  const oursSecs = splitMarkdown(ours);
  const theirsSecs = splitMarkdown(theirs);
  const baseIndex = indexSections(splitMarkdown(base));
  const keysLeft = oursSecs.map(sectionKey);
  const keysRight = theirsSecs.map(sectionKey);
  const regions: Merge3Region[] = [];
  for (const op of opcodes(keysLeft, keysRight)) {
    if (op.tag === "equal") {
      for (let i = op.i1; i < op.i2; i++) {
        const oursText = oursSecs[i] ?? "";
        const theirsText = theirsSecs[op.j1 + (i - op.i1)] ?? "";
        const baseText = takeBase(baseIndex, keysLeft[i] ?? "");
        regions.push(...merge3Lines(baseText, oursText, theirsText));
      }
      continue;
    }
    for (const oursText of oursSecs.slice(op.i1, op.i2)) {
      const baseText = takeBase(baseIndex, sectionKey(oursText));
      regions.push(...merge3Lines(baseText, oursText, ""));
    }
    for (const theirsText of theirsSecs.slice(op.j1, op.j2)) {
      const baseText = takeBase(baseIndex, sectionKey(theirsText));
      regions.push(...merge3Lines(baseText, "", theirsText));
    }
  }
  return coalesce(regions);
}

/**
 * 有标题时先按节对齐（避免「八、目录规划」对上「八、Skill」），节内用三路行 diff。
 * 没改的行保持原样；只改官方的行自动进结果并标绿；只改现行的行标红；两边都改的行再按行 diff。
 */
export function merge3Regions(base: string, ours: string, theirs: string): Merge3Region[] {
  if (ours === theirs) {
    return ours ? [{ type: "equal", text: ours }] : [];
  }
  const oursSections = splitMarkdown(ours);
  const theirsSections = splitMarkdown(theirs);
  if (hasHeading(oursSections) && hasHeading(theirsSections)) {
    return mergeSections(base || "", ours, theirs);
  }
  return merge3Lines(base || "", ours, theirs);
}
