import type { ConversationSummary } from "../api";
import { displayYmd, ymdInDisplayZone } from "./displayTime";

export type ConversationGroup = {
  label: string;
  items: ConversationSummary[];
};

type Ymd = { y: number; m: number; d: number };

function daysBetween(earlier: Ymd, later: Ymd): number {
  const t0 = Date.UTC(earlier.y, earlier.m - 1, earlier.d);
  const t1 = Date.UTC(later.y, later.m - 1, later.d);
  return Math.round((t1 - t0) / 86_400_000);
}

/** 按 updated_at 将会话列表分组：今天 / 昨天 / 近7日 / 更早（按月，北京时间日历）。 */
export function groupConversationsByTime(
  conversations: ConversationSummary[],
  now = new Date(),
): ConversationGroup[] {
  const today = ymdInDisplayZone(now);

  const groups = new Map<string, ConversationSummary[]>();
  const order: string[] = [];

  for (const c of conversations) {
    const d = displayYmd(c.updated_at);
    let label: string;
    if (!d) {
      label = "更早";
    } else {
      const age = daysBetween(d, today);
      if (age <= 0) {
        label = "今天";
      } else if (age === 1) {
        label = "昨天";
      } else if (age <= 7) {
        label = "近7日";
      } else {
        label = `${d.y}年${d.m}月`;
      }
    }
    if (!groups.has(label)) {
      groups.set(label, []);
      order.push(label);
    }
    groups.get(label)!.push(c);
  }

  return order.map((label) => ({ label, items: groups.get(label)! }));
}
