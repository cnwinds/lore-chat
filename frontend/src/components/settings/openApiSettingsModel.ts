export type VoiceMode = "default" | "existing" | "new" | "copy";
export type ChannelIngress = "websocket" | "http_webhook";

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
  ingress: ChannelIngress;
  botToken: string;
  signingSecret: string;
  appToken: string;
  corpId: string;
  agentId: string;
  corpSecret: string;
  wecomToken: string;
  encodingAesKey: string;
  appKey: string;
  dingAppSecret: string;
  robotCode: string;
  sandboxAllowSenders: string;
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
  botToken: "",
  signingSecret: "",
  appToken: "",
  corpId: "",
  agentId: "",
  corpSecret: "",
  wecomToken: "",
  encodingAesKey: "",
  appKey: "",
  dingAppSecret: "",
  robotCode: "",
  sandboxAllowSenders: "",
};

function withSandbox(config: Record<string, string>, draft: CreateKeyDraft) {
  const senders = draft.sandboxAllowSenders.trim();
  return senders ? { ...config, sandbox_allow_senders: senders } : config;
}

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
  if (typeId === "slack") {
    if (!draft.botToken.trim()) return false;
    if (draft.ingress === "http_webhook") return Boolean(draft.signingSecret.trim());
    return Boolean(draft.appToken.trim());
  }
  if (typeId === "wecom") {
    return Boolean(
      draft.corpId.trim() &&
        draft.agentId.trim() &&
        draft.corpSecret.trim() &&
        draft.wecomToken.trim() &&
        draft.encodingAesKey.trim(),
    );
  }
  if (typeId === "dingtalk") {
    return Boolean(draft.appKey.trim() && draft.dingAppSecret.trim());
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
    config: withSandbox(
      {
        app_id: draft.appId.trim(),
        ingress: draft.ingress,
      },
      draft,
    ),
    secrets: {
      app_secret: draft.appSecret.trim(),
      ...(draft.verificationToken.trim()
        ? { verification_token: draft.verificationToken.trim() }
        : {}),
      ...(draft.encryptKey.trim() ? { encrypt_key: draft.encryptKey.trim() } : {}),
    },
  };
}

export function buildSlackConfig(draft: CreateKeyDraft) {
  return {
    config: withSandbox({ ingress: draft.ingress }, draft),
    secrets: {
      bot_token: draft.botToken.trim(),
      ...(draft.signingSecret.trim()
        ? { signing_secret: draft.signingSecret.trim() }
        : {}),
      ...(draft.appToken.trim() ? { app_token: draft.appToken.trim() } : {}),
    },
  };
}

export function buildWecomConfig(draft: CreateKeyDraft) {
  return {
    config: withSandbox(
      {
        corp_id: draft.corpId.trim(),
        agent_id: draft.agentId.trim(),
      },
      draft,
    ),
    secrets: {
      corp_secret: draft.corpSecret.trim(),
      token: draft.wecomToken.trim(),
      encoding_aes_key: draft.encodingAesKey.trim(),
    },
  };
}

export function buildDingtalkConfig(draft: CreateKeyDraft) {
  return {
    config: withSandbox(
      {
        app_key: draft.appKey.trim(),
        ingress: draft.ingress,
        ...(draft.robotCode.trim() ? { robot_code: draft.robotCode.trim() } : {}),
      },
      draft,
    ),
    secrets: {
      app_secret: draft.dingAppSecret.trim(),
    },
  };
}

export function buildTypeConfig(typeId: string, draft: CreateKeyDraft) {
  if (typeId === "feishu") return buildFeishuConfig(draft);
  if (typeId === "slack") return buildSlackConfig(draft);
  if (typeId === "wecom") return buildWecomConfig(draft);
  if (typeId === "dingtalk") return buildDingtalkConfig(draft);
  return {};
}

export function chatCurlExample(token = "lc_live_…"): string {
  return [
    `curl -sS -X POST "$LORECHAT_URL/api/v1/chat" \\`,
    `  -H "Authorization: Bearer ${token}" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '{"message":"你好"}'`,
  ].join("\n");
}

export function channelNextSteps(typeId: string): string | null {
  if (typeId === "feishu") {
    return "已按长连接接入。请在飞书开放平台开启「长连接」接收事件；无需公网回调地址。";
  }
  if (typeId === "slack") {
    return "默认 Socket Mode。请在 Slack 应用开启 Socket Mode，并订阅 message / app_mention。群/频道仅 @ 或 thread 回复才会开回合。";
  }
  if (typeId === "wecom") {
    return "请把卡片上的回调 URL 配到企业微信应用。启用前需要设置里的公网根地址。群聊仅被 @ 才回复，默认关沙箱。";
  }
  if (typeId === "dingtalk") {
    return "已按 Stream 长连接接入。请在钉钉开放平台为机器人开启 Stream。群聊需 @ 机器人。";
  }
  return null;
}

export function feishuNextSteps(): string {
  return channelNextSteps("feishu") || "";
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
