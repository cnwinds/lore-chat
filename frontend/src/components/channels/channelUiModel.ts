import type { ApiPersona } from "../../api/openApi";
import type { ChannelInstance, ChannelType } from "../../api/channelPlugins";
import { channelNextSteps, chatCurlExample } from "../settings/openApiSettingsModel";

export const TYPE_MARK: Record<string, string> = {
  script_api: "脚",
  feishu: "飞",
  slack: "S",
  wecom: "企",
  dingtalk: "钉",
  wechat_mp: "公",
};

export const NEW_EXCLUSIVE_VALUE = "__new_exclusive__";

export type DetailTab = "guide" | "sessions" | "logs" | "revoke";

export function typeLabel(typeId: string, types: ChannelType[]): string {
  return types.find((item) => item.type_id === typeId)?.display_name || typeId;
}

export function statusLabel(inst: ChannelInstance): { text: string; kind: string } {
  if (inst.status === "error") {
    return { text: inst.status_detail || "校验失败", kind: "error" };
  }
  if (inst.enabled) return { text: "已启用", kind: "enabled" };
  return { text: "未启用", kind: "disabled" };
}

export function personaUsage(instances: ChannelInstance[]): Map<string, string[]> {
  const map = new Map<string, string[]>();
  for (const inst of instances) {
    const pid = inst.persona_id || "";
    if (!pid) continue;
    const list = map.get(pid) || [];
    list.push(inst.id);
    map.set(pid, list);
  }
  return map;
}

export function isExclusiveTo(
  personaId: string,
  instanceId: string,
  usage: Map<string, string[]>,
): boolean {
  const ids = usage.get(personaId) || [];
  return ids.length === 1 && ids[0] === instanceId;
}

export function personasSelectableFor(
  personas: ApiPersona[],
  instanceId: string,
  usage: Map<string, string[]>,
): ApiPersona[] {
  return personas.filter((persona) => {
    const ids = usage.get(persona.id) || [];
    if (ids.length === 1 && ids[0] !== instanceId) return false;
    return true;
  });
}

export function personaOptionLabel(
  persona: ApiPersona,
  instanceId: string,
  usage: Map<string, string[]>,
): string {
  if (isExclusiveTo(persona.id, instanceId, usage)) {
    return `本通道专属 · ${persona.name}`;
  }
  return `${persona.name}（共用）`;
}

export function credentialChip(inst: ChannelInstance): { kind: "token" | "secrets"; text: string } {
  if (inst.type_id === "script_api") {
    const prefix = inst.config?.key_prefix || "KEY";
    const text = prefix.endsWith("…") ? prefix : `${prefix}…`;
    return { kind: "token", text };
  }
  return { kind: "secrets", text: "凭证 App ID / Secret 已保存" };
}

export function revokeTabLabel(typeId: string): string {
  return typeId === "script_api" ? "吊销" : "删除";
}

export function accessGuide(typeId: string): {
  lead: string;
  steps: string[];
  extra: string | null;
  curl: string | null;
} {
  if (typeId === "script_api") {
    return {
      lead: "用调用 Key 请求 POST /api/v1/chat ，Header 写 Authorization: Bearer <key> 。",
      steps: [
        "复制上方 Key（随时可再复制，无需重新生成）",
        "按 JSON 发送 { \"message\": \"…\" }；可带 conversation_id 续聊",
        "排查时切到「日志」",
      ],
      extra: null,
      curl: chatCurlExample(),
    };
  }
  return {
    lead: channelNextSteps(typeId) || "按该类型的接入步骤完成配置后即可收发消息。",
    steps: ["核对卡片上的凭证或回调地址", "启用通道后再从外部发一条消息试通", "排查时切到「日志」"],
    extra: null,
    curl: null,
  };
}
