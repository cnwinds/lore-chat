/**
 * 各厂家 API Key 管理页（新标签打开）。
 * custom / 未知厂家无链接。
 */
export const PROVIDER_API_KEY_URLS: Record<string, string> = {
  openai: "https://platform.openai.com/api-keys",
  zhipu: "https://open.bigmodel.cn/usercenter/proj-mgmt/apikeys",
  bailian: "https://bailian.console.aliyun.com/?tab=model#/api-key",
  deepseek: "https://platform.deepseek.com/api_keys",
  agnes: "https://platform.agnes-ai.com/",
  openrouter: "https://openrouter.ai/settings/keys",
  siliconflow: "https://cloud.siliconflow.cn/account/ak",
  tavily: "https://app.tavily.com/home",
  serper: "https://serper.dev/api-keys",
  brave: "https://api-dashboard.search.brave.com/app/keys",
};

/** 已知厂家返回 Key 管理页 URL；custom / 未知返回 null。 */
export function providerApiKeyUrl(providerId: string): string | null {
  const id = providerId.trim().toLowerCase();
  if (!id || id === "custom") return null;
  return PROVIDER_API_KEY_URLS[id] ?? null;
}
