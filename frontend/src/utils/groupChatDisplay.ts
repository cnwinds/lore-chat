import type { ChatMessage, RoleSummary, RoomParticipant } from "../types/chat";

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
