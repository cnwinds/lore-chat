import { describe, expect, it } from "vitest";
import {
  formatSkillHeaderEntries,
  isSkillMdPath,
  joinSkillBody,
  parseSkillYamlMapping,
  splitSkillBodyHeader,
} from "./skillHeader";

describe("isSkillMdPath", () => {
  it("matches SKILL.md entry paths", () => {
    expect(isSkillMdPath("技能/demo/SKILL.md")).toBe(true);
    expect(isSkillMdPath("SKILL.md")).toBe(true);
    expect(isSkillMdPath("技能/demo/readme.md")).toBe(false);
    expect(isSkillMdPath("技能/demo/skill.md")).toBe(false);
  });
});

describe("splitSkillBodyHeader", () => {
  it("splits YAML header and keeps raw block for round-trip", () => {
    const body = `---
name: demo-skill
description: |
  line one
  line two
starter_prompts:
  - 你好
  - 帮我看看
---

# Title

正文
`;
    const split = splitSkillBodyHeader(body);
    expect(split.headerBlock).toMatch(/^---\n[\s\S]*\n---\n$/);
    expect(split.content).toBe("\n# Title\n\n正文\n");
    expect(split.fields.map((f) => f.key)).toEqual([
      "name",
      "description",
      "starter_prompts",
    ]);
    expect(split.fields[0]).toEqual({
      key: "name",
      label: "名称",
      value: "demo-skill",
    });
    expect(split.fields[1].value).toBe("line one\nline two");
    expect(split.fields[2].value).toEqual(["你好", "帮我看看"]);
    expect(joinSkillBody(split.headerBlock, split.content)).toBe(body);
  });

  it("returns whole body when no skill header", () => {
    const body = "# plain\n\nhello\n";
    const split = splitSkillBodyHeader(body);
    expect(split.headerBlock).toBeNull();
    expect(split.fields).toEqual([]);
    expect(split.content).toBe(body);
  });

  it("handles single-line description", () => {
    const body = `---
name: how-to-read-a-book
description: Use when the user asks to read a book together.
---
# 怎样阅读一本书
`;
    const split = splitSkillBodyHeader(body);
    expect(split.fields[1].value).toContain("read a book");
    expect(split.content.startsWith("# 怎样阅读一本书")).toBe(true);
  });

  it("still strips header when YAML mapping is empty or invalid", () => {
    const body = `---
: not valid enough
---
# Body
`;
    const split = splitSkillBodyHeader(body);
    expect(split.headerBlock).not.toBeNull();
    expect(split.content.startsWith("# Body")).toBe(true);
    // 字段可空，但不得把 header 留在 content 里
    expect(split.content.includes("---")).toBe(false);
  });

  it("strips comment-only header and keeps opaque block", () => {
    const body = `---
# only a comment
---
正文
`;
    const split = splitSkillBodyHeader(body);
    expect(split.headerBlock).toMatch(/^---\n/);
    expect(split.fields).toEqual([]);
    expect(split.content).toBe("正文\n");
  });
});

describe("parseSkillYamlMapping", () => {
  it("parses inline list", () => {
    expect(parseSkillYamlMapping("tags: [a, b]\n")).toEqual({
      tags: ["a", "b"],
    });
  });

  it("returns empty object on invalid YAML", () => {
    expect(parseSkillYamlMapping("[[[\n")).toEqual({});
  });

  it("drops empty keys from permissive parses", () => {
    expect(parseSkillYamlMapping(":\n  -")).toEqual({});
  });
});

describe("formatSkillHeaderEntries", () => {
  it("orders known keys first and keeps list values as arrays", () => {
    const entries = formatSkillHeaderEntries({
      starter_prompts: ["x"],
      name: "n",
      description: "d",
      custom: "c",
    });
    expect(entries.map((e) => e.label)).toEqual([
      "名称",
      "描述",
      "启动提示",
      "custom",
    ]);
    expect(entries[2].value).toEqual(["x"]);
  });
});
