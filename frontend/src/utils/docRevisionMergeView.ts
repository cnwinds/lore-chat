import { diffLines } from "diff";
import { buildDocDiff } from "./docDiff";
import { changeCounts, lineRange, type ConflictSides } from "./preceptsMergeView";

export type RevisionMergeModel = {
  older: string;
  newer: string;
  draft: string;
  conflicts: ConflictSides[];
};

/** 相邻删+增视为一块冲突（同段替换），纯增/纯删自动合并。 */
export function replaceConflicts(older: string, newer: string): ConflictSides[] {
  const changes = diffLines(older, newer);
  const conflicts: ConflictSides[] = [];
  for (let i = 0; i < changes.length; i++) {
    const rem = changes[i];
    const add = changes[i + 1];
    if (rem?.removed && add?.added) {
      conflicts.push({
        base: rem.value,
        ours: rem.value,
        theirs: add.value,
      });
      i += 1;
    }
  }
  return conflicts;
}

export function buildRevisionMergeModel(
  older: string,
  newer: string,
): RevisionMergeModel {
  const conflicts = replaceConflicts(older, newer);
  return { older, newer, draft: newer, conflicts };
}

export function revisionDiffSummary(older: string, newer: string): {
  changes: number;
  conflicts: number;
} {
  const lines = buildDocDiff(older, newer);
  const { plus, minus } = changeCounts(lines);
  return {
    changes: plus + minus,
    conflicts: replaceConflicts(older, newer).length,
  };
}

export type SideLineTone = "plain" | "change" | "conflict";

export function sideLineTonesForRevision(
  older: string,
  newer: string,
  conflicts: ConflictSides[],
): { older: SideLineTone[]; newer: SideLineTone[] } {
  const olderLines = (older || "").split("\n");
  const newerLines = (newer || "").split("\n");
  const olderTones: SideLineTone[] = olderLines.map(() => "plain");
  const newerTones: SideLineTone[] = newerLines.map(() => "plain");

  for (const hunk of conflicts) {
    const left = lineRange(older, hunk.ours);
    const right = lineRange(newer, hunk.theirs);
    if (left) {
      for (let i = left.start; i < left.end && i < olderTones.length; i++) {
        olderTones[i] = "conflict";
      }
    }
    if (right) {
      for (let i = right.start; i < right.end && i < newerTones.length; i++) {
        newerTones[i] = "conflict";
      }
    }
  }

  const changes = diffLines(older, newer);
  let olderIdx = 0;
  let newerIdx = 0;
  for (const change of changes) {
    const parts = change.value.split("\n");
    const lineCount =
      parts.length > 0 && parts[parts.length - 1] === ""
        ? parts.length - 1
        : parts.length;
    if (change.removed) {
      for (let k = 0; k < lineCount; k++) {
        if (olderTones[olderIdx + k] === "plain") {
          olderTones[olderIdx + k] = "change";
        }
      }
      olderIdx += lineCount;
    } else if (change.added) {
      for (let k = 0; k < lineCount; k++) {
        if (newerTones[newerIdx + k] === "plain") {
          newerTones[newerIdx + k] = "change";
        }
      }
      newerIdx += lineCount;
    } else {
      olderIdx += lineCount;
      newerIdx += lineCount;
    }
  }

  return { older: olderTones, newer: newerTones };
}
