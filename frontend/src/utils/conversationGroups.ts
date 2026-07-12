import type { ConversationSummary } from "../api";

export type ConversationGroup = {
  label: string;
  items: ConversationSummary[];
};

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function addDays(d: Date, days: number): Date {
  const next = new Date(d);
  next.setDate(next.getDate() + days);
  return next;
}

/** 按 updated_at 将会话列表分组：今天 / 昨天 / 近7日 / 更早（按月）。 */
export function groupConversationsByTime(
  conversations: ConversationSummary[],
  now = new Date(),
): ConversationGroup[] {
  const startToday = startOfDay(now);
  const startYesterday = addDays(startToday, -1);
  const startWeek = addDays(startToday, -7);

  const groups = new Map<string, ConversationSummary[]>();
  const order: string[] = [];

  for (const c of conversations) {
    const d = new Date(c.updated_at);
    let label: string;
    if (Number.isNaN(d.getTime())) {
      label = "更早";
    } else if (d >= startToday) {
      label = "今天";
    } else if (d >= startYesterday) {
      label = "昨天";
    } else if (d >= startWeek) {
      label = "近7日";
    } else {
      label = `${d.getFullYear()}年${d.getMonth() + 1}月`;
    }
    if (!groups.has(label)) {
      groups.set(label, []);
      order.push(label);
    }
    groups.get(label)!.push(c);
  }

  return order.map((label) => ({ label, items: groups.get(label)! }));
}
