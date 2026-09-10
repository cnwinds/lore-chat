/** 左栏副标题只用人设，不用最后一条消息。 */
export function rolePersonaPreview(role: {
  system_prompt?: string | null;
}): string {
  return (role.system_prompt || "").replace(/\s+/g, " ").trim();
}

function activityStamp(role: {
  last_active_at?: string | null;
  updated_at?: string;
  created_at?: string;
}): string {
  return role.last_active_at || role.updated_at || role.created_at || "";
}

/** 最近有会话活动的角色排在上面。 */
export function sortRolesByRecentActivity<
  T extends {
    last_active_at?: string | null;
    updated_at?: string;
    created_at?: string;
    sort_order?: number;
  },
>(roles: T[]): T[] {
  return [...roles].sort((a, b) => {
    const tb = activityStamp(b);
    const ta = activityStamp(a);
    if (ta !== tb) return tb.localeCompare(ta);
    return (a.sort_order ?? 0) - (b.sort_order ?? 0);
  });
}
