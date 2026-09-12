import { openJson as apiFetch } from "../lib/httpTransport";
import { getRoleTimeline, type RoleTimeline } from "../api";

export type ApiPersona = {
  id: string;
  name: string;
  avatar?: string | null;
  system_prompt: string;
  created_at: string;
  updated_at: string;
};

export type OpenApiKey = {
  id: string;
  name: string;
  prefix: string;
  persona_id?: string | null;
  role_id?: string | null;
  revoked: boolean;
  created_at: string;
  last_used_at?: string | null;
  persona?: ApiPersona | null;
  token?: string;
};

export function listApiPersonas() {
  return apiFetch<{ personas: ApiPersona[] }>("/api/open-api/personas");
}

export function createApiPersona(body: {
  name: string;
  system_prompt?: string;
  avatar?: string | null;
  from_role_id?: string | null;
}) {
  return apiFetch<ApiPersona>("/api/open-api/personas", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function updateApiPersona(
  id: string,
  body: { name?: string; system_prompt?: string; avatar?: string | null },
) {
  return apiFetch<ApiPersona>(`/api/open-api/personas/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function deleteApiPersona(id: string) {
  return apiFetch<{ ok: boolean }>(`/api/open-api/personas/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function listOpenApiKeys() {
  return apiFetch<{ keys: OpenApiKey[] }>("/api/open-api/keys");
}

export function createOpenApiKey(body: {
  name: string;
  persona_id?: string | null;
  persona_name?: string;
  persona_prompt?: string;
}) {
  return apiFetch<OpenApiKey>("/api/open-api/keys", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function revokeOpenApiKey(id: string) {
  return apiFetch<OpenApiKey>(`/api/open-api/keys/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function getOpenApiKeyTimeline(roleId: string): Promise<RoleTimeline> {
  return getRoleTimeline(roleId, {
    includeMessages: true,
    limit: 20,
    messageLimit: 0,
  });
}
