export type VoiceMode = "default" | "existing" | "new" | "copy";

export type CreateKeyDraft = {
  name: string;
  voice: VoiceMode;
  personaId: string;
  personaName: string;
  personaPrompt: string;
  copyRoleId: string;
};

export type CreateKeyRequest = {
  name: string;
  persona_id?: string;
  persona_name?: string;
  persona_prompt?: string;
};

export const EMPTY_CREATE_DRAFT: CreateKeyDraft = {
  name: "",
  voice: "default",
  personaId: "",
  personaName: "",
  personaPrompt: "",
  copyRoleId: "",
};

export function canSubmitCreateKey(draft: CreateKeyDraft): boolean {
  if (!draft.name.trim()) return false;
  if (draft.voice === "existing") return Boolean(draft.personaId);
  if (draft.voice === "new") return Boolean(draft.personaName.trim());
  if (draft.voice === "copy") return Boolean(draft.copyRoleId);
  return true;
}

export function buildCreateKeyRequest(draft: CreateKeyDraft): CreateKeyRequest {
  const name = draft.name.trim();
  if (draft.voice === "existing") {
    return { name, persona_id: draft.personaId };
  }
  if (draft.voice === "new") {
    return {
      name,
      persona_name: draft.personaName.trim(),
      persona_prompt: draft.personaPrompt,
    };
  }
  return { name };
}

export function chatCurlExample(token = "lc_live_…"): string {
  return [
    `curl -sS -X POST "$LORECHAT_URL/api/v1/chat" \\`,
    `  -H "Authorization: Bearer ${token}" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '{"message":"你好"}'`,
  ].join("\n");
}

export function formatOpenApiWhen(iso?: string | null): string {
  if (!iso) return "尚未调用";
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return iso;
  return new Date(ms).toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
