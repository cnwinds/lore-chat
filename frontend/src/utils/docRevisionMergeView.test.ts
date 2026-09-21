import { describe, expect, it } from "vitest";
import {
  buildRevisionMergeModel,
  replaceConflicts,
  revisionDiffSummary,
  sideLineTonesForRevision,
} from "./docRevisionMergeView";

describe("docRevisionMergeView", () => {
  it("treats replace hunks as conflicts", () => {
    const conflicts = replaceConflicts("A\nold\n", "A\nnew\n");
    expect(conflicts).toHaveLength(1);
    expect(conflicts[0]?.ours).toContain("old");
    expect(conflicts[0]?.theirs).toContain("new");
  });

  it("auto-merges pure insertions", () => {
    const model = buildRevisionMergeModel("A\n", "A\nB\n");
    expect(model.conflicts).toHaveLength(0);
    expect(model.draft).toBe("A\nB\n");
  });

  it("marks non-conflict edits green on the right", () => {
    const tones = sideLineTonesForRevision("A\n", "A\nB\n", []);
    expect(tones.newer[1]).toBe("change");
  });

  it("summarizes change and conflict counts", () => {
    expect(revisionDiffSummary("A\nold\n", "A\nnew\n")).toEqual({
      changes: 2,
      conflicts: 1,
    });
  });
});
