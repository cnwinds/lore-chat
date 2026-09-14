import { openJson as apiFetch } from "../lib/httpTransport";
import { getRoleTimeline, type RoleTimeline } from "../api";
import type { ApiPersona } from "./openApi";

export type ChannelType = {
  type_id: string;
  display_name: string;
  ingress: string;
  needs_public_url: boolean;
  available: boolean;
};

export type ChannelInstance = {
  id: string;
  type_id: string;
  name: string;
  enabled: boolean;
  status: "disabled" | "enabled" | "error" | string;
  status_detail?: string | null;
  persona_id?: string | null;
  role_id?: string | null;
  created_at: string;
  last_event_at?: string | null;
  config?: { key_prefix?: string };
  persona?: ApiPersona | null;
  token?: string;
};

export function listChannelTypes() {
  return apiFetch<{ types: ChannelType[] }>("/api/channel-plugins/types");
}

export function listChannelInstances() {
  return apiFetch<{ instances: ChannelInstance[] }>("/api/channel-plugins/instances");
}

export function createChannelInstance(body: {
  type_id: string;
  name: string;
  persona_id?: string | null;
  persona_name?: string;
  persona_prompt?: string;
}) {
  return apiFetch<ChannelInstance>("/api/channel-plugins/instances", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function revokeChannelInstance(id: string) {
  return apiFetch<ChannelInstance>(
    `/api/channel-plugins/instances/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
}

export function getChannelTimeline(roleId: string): Promise<RoleTimeline> {
  return getRoleTimeline(roleId, {
    includeMessages: true,
    limit: 20,
    messageLimit: 0,
  });
}
