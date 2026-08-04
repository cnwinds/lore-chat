import { describe, expect, it } from "vitest";
import { formatMetaEntries } from "./docMeta";

describe("formatMetaEntries", () => {
  it("orders created before updated and uses Chinese labels", () => {
    const entries = formatMetaEntries({
      updated: "2026-07-11T21:58:53",
      title: "报告",
      created: "2026-07-10T10:00:00",
      tags: ["AIGC"],
    });
    expect(entries.map((e) => e.label)).toEqual([
      "标题",
      "创建时间",
      "更新时间",
      "标签",
    ]);
    expect(entries[1].value).toBe("2026-07-10 10:00:00");
  });
});
