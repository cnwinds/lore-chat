/** 人设修订 source 字段 → 界面标签（与 P2 契约一致）。 */
export const PERSONA_REVISION_SOURCE_LABELS: Record<string, string> = {
  baseline: "初始",
  create: "创建",
  manual: "主人修改",
  tool: "对话中修改",
  onboarding: "引导定稿",
  evolution: "自动进化",
  rollback: "回退",
};

export function personaRevisionSourceLabel(source: string): string {
  return PERSONA_REVISION_SOURCE_LABELS[source] ?? source;
}
