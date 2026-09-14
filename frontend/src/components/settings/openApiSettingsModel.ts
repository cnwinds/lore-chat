export type VoiceMode = "default" | "existing" | "new" | "copy";

export type CreateKeyDraft = {
  name: string;
  voice: VoiceMode;
  personaId: string;
  personaName: string;
  personaPrompt: string;
  copyRoleId: string;
  appId: string;
  appSecret: string;
  verificationToken: string;
  encryptKey: string;
  ingress: "websocket" | "http_webhook";
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
  appId: "",
  appSecret: "",
  verificationToken: "",
  encryptKey: "",
  ingress: "websocket",
};

export function canSubmitCreateKey(
  draft: CreateKeyDraft,
  typeId = "script_api",
): boolean {
  if (!draft.name.trim()) return false;
  if (draft.voice === "existing" && !draft.personaId) return false;
  if (draft.voice === "new" && !draft.personaName.trim()) return false;
  if (draft.voice === "copy" && !draft.copyRoleId) return false;
  if (typeId === "feishu") {
    return Boolean(draft.appId.trim() && draft.appSecret.trim());
  }
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

export function buildFeishuConfig(draft: CreateKeyDraft) {
  return {
    config: {
      app_id: draft.appId.trim(),
      ingress: draft.ingress,
    },
    secrets: {
      app_secret: draft.appSecret.trim(),
      ...(draft.verificationToken.trim()
        ? { verification_token: draft.verificationToken.trim() }
        : {}),
      ...(draft.encryptKey.trim() ? { encrypt_key: draft.encryptKey.trim() } : {}),
    },
  };
}

export function chatCurlExample(token = "lc_live_…"): string {
  return [
    `curl -sS -X POST "$LORECHAT_URL/api/v1/chat" \\`,
    `  -H "Authorization: Bearer ${token}" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '{"message":"你好"}'`,
  ].join("\n");
}

export function feishuNextSteps(): string {
  return "已按长连接接入。请在飞书开放平台开启「长连接」接收事件；无需公网回调地址。";
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
