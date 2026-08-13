import { describe, expect, it } from "vitest";
import { discoverSkillRoots, enclosingSkillRoot } from "./kbSkill";

describe("discoverSkillRoots", () => {
  const paths = [
    "技能/职业规划/张雪峰/SKILL.md",
    "技能/other/SKILL.md",
    "技能/怎样阅读一本书.md",
  ];

  it("finds nested packages under folder", () => {
    const found = discoverSkillRoots(paths, "技能");
    expect(found).toHaveLength(2);
    expect(found).toContain("技能/other");
    expect(found).toContain("技能/职业规划/张雪峰");
  });

  it("ignores lone md without SKILL.md dir", () => {
    expect(discoverSkillRoots(paths, "技能")).not.toContain(
      "技能/怎样阅读一本书",
    );
  });
});

describe("enclosingSkillRoot", () => {
  it("detects package for reference file", () => {
    const paths = ["技能/foo/SKILL.md", "技能/foo/references/x.md"];
    expect(enclosingSkillRoot("技能/foo/references/x.md", paths)).toBe(
      "技能/foo",
    );
  });
});
