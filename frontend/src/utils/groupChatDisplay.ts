import type { ChatMessage, RoleSummary, RoomParticipant } from "../types/chat";
import type { MentionCandidate } from "./roleMentions";

export function mentionCandidatesForRoom(opts: {
  roomMode: "role" | "group";
  roles: RoleSummary[];
  participants: RoomParticipant[];
}): MentionCandidate[] {
  const { roomMode, roles, participants } = opts;
  if (roomMode === "group") {
    return participants.map((p) => {
      const role = roles.find((r) => r.id === p.id);
      return {
        id: p.id,
        name: role?.name || p.name,
        avatar: role?.avatar ?? p.avatar ?? null,
      };
    });
  }
  return roles.map((r) => ({
    id: r.id,
    name: r.name,
    avatar: r.avatar,
  }));
}

export function defaultGroupTitle(
  roles: Array<{ id: string; name: string }>,
  roleIds: string[],
): string {
  const names = roleIds
    .map((id) => roles.find((r) => r.id === id)?.name?.trim())
    .filter((name): name is string => Boolean(name));
  if (names.length === 0) return "群聊";
  if (names.length <= 3) return names.join("、");
  return `${names.slice(0, 3).join("、")} 等`;
}

export function membersFromRoleIds(
  ids: string[] | undefined,
  roles: RoleSummary[],
  fallback?: RoomParticipant[],
): RoomParticipant[] {
  if (fallback && fallback.length) return fallback;
  return (ids || []).map((id) => {
    const role = roles.find((r) => r.id === id);
    return { id, name: role?.name || id, avatar: role?.avatar };
  });
}

export function isOwnerSpeaker(message: ChatMessage): boolean {
  if (message.speaker_kind === "user") return true;
  return message.role === "user" && message.speaker_kind !== "role";
}

/** 协作卡预览不展示 conversation:// 房间 id，避免窄屏撑破边框。 */
export function sanitizeCollabPreview(text: string): string {
  return (text || "")
    .replace(/conversation:\/\/[a-f0-9-]+/gi, "")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function resolveGroupSpeaker(
  message: ChatMessage,
  roles: RoleSummary[],
  respondingRoleId?: string | null,
): { kind: "owner" | "role"; role?: RoleSummary; name: string; id?: string } {
  if (isOwnerSpeaker(message)) {
    return { kind: "owner", name: "主人" };
  }
  const sid =
    (message.speaker_id || "").trim() ||
    (message.role === "assistant" ? (respondingRoleId || "").trim() : "");
  const role = sid ? roles.find((r) => r.id === sid) : undefined;
  return {
    kind: "role",
    role,
    id: sid || role?.id,
    name: message.speaker_name || role?.name || "角色",
  };
}
