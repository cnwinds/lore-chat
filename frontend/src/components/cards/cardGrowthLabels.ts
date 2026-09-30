import type { CardGrowthAction, CardGrowthEntry } from "../../api";

export const CARD_GROWTH_ENTRY_LABELS: Record<CardGrowthEntry["kind"], string> =
  {
    learned: "学到",
    consolidated: "整理",
    faded: "淡出",
    persona: "人设",
    proposal: "提议",
  };

export const CARD_GROWTH_ACTION_LABELS: Record<CardGrowthAction, string> = {
  new: "新学",
  revised: "修正",
  promoted: "转正",
  revived: "恢复",
  merged: "合并",
  abstracted: "抽象",
  qualified: "补条件",
  superseded: "取代",
  expired: "过期",
  dropped: "作废",
  demoted: "转回待印证",
};

export function cardGrowthSourcesLabel(
  action: CardGrowthAction,
  count: number,
): string {
  if (action === "superseded") return `取代了 ${count} 张卡`;
  return `由 ${count} 张卡整理而来`;
}
