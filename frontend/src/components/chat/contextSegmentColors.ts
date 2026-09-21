/** 分项配色（与后端 segments 顺序对应）：系统=琥珀、记忆=绛红、Skill=金、历史=青釉、工具=钴蓝、附件=藕紫。 */
export const SEGMENT_COLORS: Record<string, string> = {
  system: "var(--system-layer)",
  memory: "var(--ctx-memory)",
  skill: "var(--ctx-skill)",
  history: "var(--glaze)",
  tools: "var(--ctx-tools)",
  attachments: "var(--ctx-att)",
};

export function segmentColor(key: string): string {
  return SEGMENT_COLORS[key] ?? "var(--text-muted)";
}
