import { describe, expect, it } from "vitest";
import { discoverSkillRoots, enclosingSkillRoot } from "./kbSkill";

describe("discoverSkillRoots", () => {
  const paths = [
    "skill/职业规划/张雪峰/SKILL.md",
    "skill/other/SKILL.md",
    "skill/怎样阅读一本书.md",
  ];

  it("finds nested packages under folder", () => {
    const found = discoverSkillRoots(paths, "skill");
    expect(found).toHaveLength(2);
    expect(found).toContain("skill/other");
    expect(found).toContain("skill/职业规划/张雪峰");
  });

  it("ignores lone md without SKILL.md dir", () => {
    expect(discoverSkillRoots(paths, "skill")).not.toContain(
      "skill/怎样阅读一本书",
    );
  });
});

describe("enclosingSkillRoot", () => {
  it("detects package for reference file", () => {
    const paths = ["skill/foo/SKILL.md", "skill/foo/references/x.md"];
    expect(enclosingSkillRoot("skill/foo/references/x.md", paths)).toBe(
      "skill/foo",
    );
  });
});
