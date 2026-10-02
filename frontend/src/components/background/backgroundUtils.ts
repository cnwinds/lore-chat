import type { BgLane, BgNode, BgOverview, BgPausable } from "../../types/background";
import { formatSearchRelativeTime } from "../../utils/displayTime";

export type PromptSegment =
  | { kind: "text"; value: string }
  | { kind: "placeholder"; value: string };

/** 中文运行时占位：`{…}` 内至少一个汉字，且不含 `"`、`[`、嵌套 `{`。 */
const PROMPT_PLACEHOLDER_RE = /\{[^{"[\]]*[\u4e00-\u9fff][^{"[\]]*\}/g;

/** 将提示词文本按约定占位切分，便于高亮。 */
export function splitPromptPlaceholders(text: string): PromptSegment[] {
  if (!text) return [];
  const parts: PromptSegment[] = [];
  const re = new RegExp(PROMPT_PLACEHOLDER_RE.source, "g");
  let last = 0;
  for (const match of text.matchAll(re)) {
    const idx = match.index ?? 0;
    if (idx > last) {
      parts.push({ kind: "text", value: text.slice(last, idx) });
    }
    parts.push({ kind: "placeholder", value: match[0] });
    last = idx + match[0].length;
  }
  if (last < text.length) {
    parts.push({ kind: "text", value: text.slice(last) });
  }
  return parts;
}

export function formatBackgroundRelativeTime(
  iso: string | null | undefined,
  now: Date = new Date(),
): string {
  if (!iso) return "尚无记录";
  return formatSearchRelativeTime(iso, now);
}

export type GroupedLanes = {
  id: BgOverview["groups"][number]["id"];
  title: string;
  hint: string;
  lanes: BgLane[];
};

export function groupOverviewLanes(overview: BgOverview): GroupedLanes[] {
  return overview.groups.map((g) => ({
    id: g.id,
    title: g.title,
    hint: g.hint,
    lanes: overview.lanes.filter((lane) => lane.group === g.id),
  }));
}

export function findLaneForNode(
  lanes: BgLane[],
  nodeId: string,
): BgLane | null {
  for (const lane of lanes) {
    for (const step of lane.steps) {
      if (step.nodes.includes(nodeId)) return lane;
    }
  }
  return null;
}

export function laneTitleById(lanes: BgLane[], laneId: string): string {
  return lanes.find((l) => l.id === laneId)?.title ?? laneId;
}

export function countChars(text: string): number {
  return [...text].length;
}

/** 泳道级 pause_key + 泳道内各节点 pause_key，去重保序。 */
export function collectLanePauseKeys(
  lane: BgLane,
  nodes: Record<string, BgNode>,
): string[] {
  const keys: string[] = [];
  const seen = new Set<string>();
  const push = (key: string | null | undefined) => {
    if (!key || seen.has(key)) return;
    seen.add(key);
    keys.push(key);
  };
  push(lane.pause_key);
  for (const step of lane.steps) {
    for (const nodeId of step.nodes) {
      push(nodes[nodeId]?.pause_key);
    }
  }
  return keys;
}

export function pauseKeyLabel(pausable: BgPausable[], key: string): string {
  return pausable.find((p) => p.key === key)?.label ?? key;
}

/** API / 旧数据可能缺少数组字段，避免详情抽屉读 .length 崩溃。 */
export function normalizeBgNode(node: BgNode): BgNode {
  return {
    ...node,
    conditions: node.conditions ?? [],
    limits: node.limits ?? [],
    prompts: (node.prompts ?? []).map((p) => ({
      ...p,
      notes: p.notes ?? [],
    })),
    guards: node.guards ?? [],
    outputs: node.outputs ?? [],
    settings: node.settings ?? [],
    constants: node.constants ?? [],
    source_files: node.source_files ?? [],
    links: node.links ?? [],
  };
}

export function normalizeBgOverview(overview: BgOverview): BgOverview {
  const nodes: Record<string, BgNode> = {};
  for (const [id, node] of Object.entries(overview.nodes)) {
    nodes[id] = normalizeBgNode(node);
  }
  return { ...overview, nodes };
}
