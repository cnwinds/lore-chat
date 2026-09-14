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
  config?: {
    key_prefix?: string;
    app_id?: string;
    ingress?: string;
  };
  secrets?: Record<string, string>;
  persona?: ApiPersona | null;
  token?: string;
};

export type ChannelLogItem = {
  id: string;
  ts: string;
  level: string;
  kind: string;
  message: string;
  extra?: Record<string, unknown> | null;
  duration_ms?: number | null;
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
  config?: Record<string, string>;
  secrets?: Record<string, string>;
  enabled?: boolean;
}) {
  return apiFetch<ChannelInstance>("/api/channel-plugins/instances", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function patchChannelInstance(
  id: string,
  body: {
    name?: string;
    persona_id?: string;
    enabled?: boolean;
    config?: Record<string, string>;
    secrets?: Record<string, string>;
  },
) {
  return apiFetch<ChannelInstance>(
    `/api/channel-plugins/instances/${encodeURIComponent(id)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

export function revokeChannelInstance(id: string) {
  return apiFetch<ChannelInstance>(
    `/api/channel-plugins/instances/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
}

export function getChannelLogs(id: string, limit = 50) {
  const q = new URLSearchParams({ limit: String(limit) });
  return apiFetch<{ items: ChannelLogItem[] }>(
    `/api/channel-plugins/instances/${encodeURIComponent(id)}/logs?${q}`,
  );
}

export function getChannelUsage(id: string) {
  return apiFetch<{
    totals?: {
      calls?: number;
      total_tokens?: number;
      cost?: number;
      cost_known_calls?: number;
    };
    by_model?: Array<{ model: string; calls?: number; total_tokens?: number; cost?: number }>;
  }>(`/api/channel-plugins/instances/${encodeURIComponent(id)}/usage`);
}

export function getChannelTimeline(roleId: string): Promise<RoleTimeline> {
  return getRoleTimeline(roleId, {
    includeMessages: true,
    limit: 20,
    messageLimit: 0,
  });
}
