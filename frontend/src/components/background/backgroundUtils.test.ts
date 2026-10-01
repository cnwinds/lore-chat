import { describe, expect, it } from "vitest";
import {
  collectLanePauseKeys,
  countChars,
  findLaneForNode,
  groupOverviewLanes,
  splitPromptPlaceholders,
} from "./backgroundUtils";
import type { BgLane, BgNode, BgOverview } from "../../types/background";

describe("splitPromptPlaceholders", () => {
  it("splits Chinese runtime placeholders", () => {
    expect(splitPromptPlaceholders("a {角色名} b")).toEqual([
      { kind: "text", value: "a " },
      { kind: "placeholder", value: "{角色名}" },
      { kind: "text", value: " b" },
    ]);
  });

  it("does not treat JSON examples as placeholders", () => {
    const text = '输出 {"items":[]} 或 {{"slot_key":"x"}}';
    expect(splitPromptPlaceholders(text)).toEqual([{ kind: "text", value: text }]);
  });

  it("highlights Chinese placeholders alongside JSON on one line", () => {
    expect(
      splitPromptPlaceholders('返回 {"items":[]}，注入 {《戒律》全文}'),
    ).toEqual([
      { kind: "text", value: '返回 {"items":[]}，注入 ' },
      { kind: "placeholder", value: "{《戒律》全文}" },
    ]);
  });

  it("returns single text segment when no placeholders", () => {
    expect(splitPromptPlaceholders("plain")).toEqual([
      { kind: "text", value: "plain" },
    ]);
  });
});

describe("groupOverviewLanes", () => {
  it("groups lanes by catalog group order", () => {
    const overview = {
      groups: [
        { id: "auto" as const, title: "自动", hint: "h1" },
        { id: "on_demand" as const, title: "按需", hint: "h2" },
      ],
      lanes: [
        { id: "b", group: "on_demand" },
        { id: "a", group: "auto" },
      ],
    } as unknown as BgOverview;
    const grouped = groupOverviewLanes(overview);
    expect(grouped.map((g) => g.lanes.map((l) => l.id))).toEqual([
      ["a"],
      ["b"],
    ]);
  });
});

describe("collectLanePauseKeys", () => {
  it("dedupes lane and node pause keys in order", () => {
    const lanes: BgLane[] = [
      {
        id: "card_maintenance",
        group: "auto",
        title: "",
        summary: "",
        cadence: "",
        worker: null,
        pause_key: null,
        steps: [{ kind: "stage", label: null, nodes: ["a", "b"] }],
      },
    ];
    const nodes = {
      a: { pause_key: "consolidation" },
      b: { pause_key: "persona_evolution" },
    } as unknown as Record<string, BgNode>;
    expect(collectLanePauseKeys(lanes[0], nodes)).toEqual([
      "consolidation",
      "persona_evolution",
    ]);
  });
});

describe("findLaneForNode", () => {
  const lanes: BgLane[] = [
    {
      id: "lane1",
      group: "auto",
      title: "T",
      summary: "",
      cadence: "",
      worker: null,
      pause_key: null,
      steps: [{ kind: "stage", label: null, nodes: ["n1", "n2"] }],
    },
  ];

  it("finds lane containing node", () => {
    expect(findLaneForNode(lanes, "n2")?.id).toBe("lane1");
    expect(findLaneForNode(lanes, "missing")).toBeNull();
  });
});

describe("countChars", () => {
  it("counts unicode code points", () => {
    expect(countChars("ab")).toBe(2);
    expect(countChars("中文")).toBe(2);
  });
});
