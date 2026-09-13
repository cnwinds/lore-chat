import type { RoleSummary, RoomSummary } from "../types/chat";

/** 左栏副标题用最近一次助手回复，不用人设。 */
export function roleReplyPreview(role: {
  last_reply_preview?: string | null;
}): string {
  return (role.last_reply_preview || "").replace(/\s+/g, " ").trim();
}

/** 群的副标题：最近一条消息；还没说话则列成员。 */
export function groupReplyPreview(room: {
  last_reply_preview?: string | null;
  participant_names?: string[];
}): string {
  const reply = roleReplyPreview(room);
  if (reply) return reply;
  return (room.participant_names || []).join("、");
}

export type InboxRoleItem = {
  kind: "role";
  id: string;
  last_active_at?: string | null;
  sort_order?: number;
  busy?: boolean;
  role: RoleSummary;
};

export type InboxGroupItem = {
  kind: "group";
  id: string;
  last_active_at?: string | null;
  sort_order?: number;
  busy?: boolean;
  room: RoomSummary;
};

export type InboxItem = InboxRoleItem | InboxGroupItem;

export function buildInboxItems(
  roles: RoleSummary[],
  rooms: RoomSummary[],
  busyRoleIds: string[] = [],
): InboxItem[] {
  const busy = new Set(busyRoleIds);
  const items: InboxItem[] = [
    ...roles.map((role) => ({
      kind: "role" as const,
      id: role.id,
      last_active_at: role.last_active_at,
      sort_order: role.sort_order,
      busy: busy.has(role.id),
      role,
    })),
    ...rooms.map((room) => ({
      kind: "group" as const,
      id: room.id,
      last_active_at: room.last_active_at || room.updated_at || null,
      sort_order: Number.MAX_SAFE_INTEGER,
      busy: false,
      room,
    })),
  ];
  return sortInboxByRecentActivity(items);
}

function activityMs(stamp?: string | null): number {
  if (!stamp) return 0;
  const ms = Date.parse(stamp);
  return Number.isFinite(ms) ? ms : 0;
}

export function sortInboxByRecentActivity<
  T extends {
    last_active_at?: string | null;
    sort_order?: number;
    busy?: boolean;
  },
>(items: T[]): T[] {
  return [...items].sort((a, b) => {
    if (Boolean(a.busy) !== Boolean(b.busy)) return a.busy ? -1 : 1;
    const da = activityMs(a.last_active_at);
    const db = activityMs(b.last_active_at);
    if (da !== db) return db - da;
    return (a.sort_order ?? 0) - (b.sort_order ?? 0);
  });
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
  return sortInboxByRecentActivity(
    roles.map((role) => ({
      ...role,
      busy: role.id ? busy.has(role.id) : false,
    })),
  );
}
