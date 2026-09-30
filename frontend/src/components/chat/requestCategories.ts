/** 请求快照类别配色（与后端 category 键一致）。 */
export const REQUEST_CATEGORY_COLORS: Record<string, string> = {
  rules: "var(--ctx-rules)",
  role: "var(--ctx-role)",
  cards: "var(--ctx-cards)",
  memory: "var(--ctx-memory)",
  skill: "var(--ctx-skill)",
  context: "var(--ctx-context)",
  history: "var(--glaze)",
  turn: "var(--ctx-turn)",
  tool_io: "var(--ctx-tool-io)",
  tools: "var(--ctx-tools)",
  unlabeled: "var(--ctx-unlabeled)",
};

export function categoryColor(key: string): string {
  return REQUEST_CATEGORY_COLORS[key] ?? "var(--text-muted)";
}
