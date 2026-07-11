import { diffLines } from "diff";

export type DiffLine = {
  type: "added" | "removed" | "unchanged";
  content: string;
};

/** 生成行级 diff，用于「查看变更」面板。 */
export function buildDocDiff(saved: string, current: string): DiffLine[] {
  const changes = diffLines(saved, current);
  const lines: DiffLine[] = [];

  for (const change of changes) {
    const type = change.added ? "added" : change.removed ? "removed" : "unchanged";
    const parts = change.value.split("\n");
    for (let i = 0; i < parts.length; i++) {
      if (i === parts.length - 1 && parts[i] === "") continue;
      lines.push({ type, content: parts[i] });
    }
  }

  return lines;
}
