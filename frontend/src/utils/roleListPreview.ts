/** 左栏副标题只用人设，不用最后一条消息。 */
export function rolePersonaPreview(role: {
  system_prompt?: string | null;
}): string {
  return (role.system_prompt || "").replace(/\s+/g, " ").trim();
}

function activityMs(stamp?: string | null): number {
  if (!stamp) return 0;
  const ms = Date.parse(stamp);
  return Number.isFinite(ms) ? ms : 0;
}

/** 最近真正开聊的角色排在上面；没聊过的排在后面，不跟人设更新时间抢位。 */
export function sortRolesByRecentActivity<
  T extends {
    id?: string;
    last_active_at?: string | null;
    sort_order?: number;
  },
>(roles: T[], busyRoleIds: string[] = []): T[] {
  const busy = new Set(busyRoleIds);
  return [...roles].sort((a, b) => {
    const aBusy = a.id ? busy.has(a.id) : false;
    const bBusy = b.id ? busy.has(b.id) : false;
    if (aBusy !== bBusy) return aBusy ? -1 : 1;
    const da = activityMs(a.last_active_at);
    const db = activityMs(b.last_active_at);
    if (da !== db) return db - da;
    return (a.sort_order ?? 0) - (b.sort_order ?? 0);
  });
}
