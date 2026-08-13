import { describe, expect, it } from "vitest";
import { discoverSkillRoots, enclosingSkillRoot, skillPackageRootFromSkillMd } from "./kbSkill";

describe("discoverSkillRoots", () => {
  const paths = [
    "技能/职业规划/张雪峰/SKILL.md",
    "技能/other/SKILL.md",
    "技能/怎样阅读一本书.md",
    "elsewhere/pkg/SKILL.md",
    "SKILL.md",
  ];

  it("finds nested packages under 技能 only", () => {
    const found = discoverSkillRoots(paths, "技能");
    expect(found).toHaveLength(2);
    expect(found).toContain("技能/other");
    expect(found).toContain("技能/职业规划/张雪峰");
    expect(found).not.toContain("elsewhere/pkg");
  });

  it("ignores lone md without SKILL.md dir", () => {
    expect(discoverSkillRoots(paths, "技能")).not.toContain(
      "技能/怎样阅读一本书",
    );
  });

  it("ignores root-level SKILL.md", () => {
    expect(skillPackageRootFromSkillMd("SKILL.md")).toBeNull();
  });
});

describe("enclosingSkillRoot", () => {
  it("detects package for reference file under 技能", () => {
    const paths = ["技能/foo/SKILL.md", "技能/foo/references/x.md"];
    expect(enclosingSkillRoot("技能/foo/references/x.md", paths)).toBe(
      "技能/foo",
    );
  });

  it("ignores packages outside 技能", () => {
    const paths = ["elsewhere/foo/SKILL.md", "elsewhere/foo/references/x.md"];
    expect(enclosingSkillRoot("elsewhere/foo/references/x.md", paths)).toBeNull();
  });
});
