import { describe, expect, it } from "vitest";
import { initialSkillSelection } from "../hooks/useEnabledSkillsAttach";

describe("initialSkillSelection", () => {
  it("selects all candidates when nothing enabled yet", () => {
    expect(initialSkillSelection(["技能/a", "技能/b"], [])).toEqual([
      "技能/a",
      "技能/b",
    ]);
  });

  it("intersects candidates with enabled", () => {
    expect(
      initialSkillSelection(["技能/a", "技能/b"], ["技能/b", "技能/c"]),
    ).toEqual(["技能/b"]);
  });

  it("allows empty intersection when enabled is non-empty", () => {
    expect(initialSkillSelection(["技能/a"], ["技能/c"])).toEqual([]);
  });
});
