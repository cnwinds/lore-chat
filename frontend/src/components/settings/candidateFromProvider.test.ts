import { describe, expect, it } from "vitest";
import {
  EMBED_PROVIDER_DEFAULT_BASE_URL,
  LLM_PROVIDER_DEFAULT_BASE_URL,
  candidateFromProvider,
  embedCandidateFromProvider,
  embedProviderLabel,
  formatVendorModelTitle,
  inferEmbedProviderFromBaseUrl,
  inferProviderFromBaseUrl,
  llmProviderLabel,
  resolvedLlmProviderLabel,
} from "./providerPresets";

describe("candidateFromProvider", () => {
  it("leaves custom preset empty for user to fill", () => {
    const c = candidateFromProvider("custom");
    expect(c.provider).toBe("custom");
    expect(c.base_url).toBe("");
    expect(c.model).toBe("");
    expect(c.provider_label).toBe("自定义");
  });

  it.each(
    Object.entries(LLM_PROVIDER_DEFAULT_BASE_URL) as [
      keyof typeof LLM_PROVIDER_DEFAULT_BASE_URL,
      string,
    ][],
  )("fills %s default base URL and provider id", (id, url) => {
    const c = candidateFromProvider(id);
    expect(c.provider).toBe(id);
    expect(c.base_url).toBe(url);
    expect(c.model).toBe("");
    expect(c.image).toBe(false);
    expect(c.thinking).toBe(false);
  });
});

describe("embedCandidateFromProvider", () => {
  it("leaves custom preset empty for user to fill", () => {
    const c = embedCandidateFromProvider("custom");
    expect(c.provider).toBe("custom");
    expect(c.base_url).toBe("");
    expect(c.model).toBe("");
    expect(c.provider_label).toBe("自定义");
  });

  it.each(
    Object.entries(EMBED_PROVIDER_DEFAULT_BASE_URL) as [
      keyof typeof EMBED_PROVIDER_DEFAULT_BASE_URL,
      string,
    ][],
  )("fills %s default base URL", (id, url) => {
    const c = embedCandidateFromProvider(id);
    expect(c.provider).toBe(id);
    expect(c.base_url).toBe(url);
    expect(c.model).toBe("");
  });
});

describe("inferProviderFromBaseUrl", () => {
  it("matches known preset URLs", () => {
    expect(inferProviderFromBaseUrl("https://api.deepseek.com")).toBe("deepseek");
    expect(inferProviderFromBaseUrl("https://api.deepseek.com/")).toBe("deepseek");
    expect(inferProviderFromBaseUrl("https://openrouter.ai/api/v1")).toBe(
      "openrouter",
    );
    expect(inferProviderFromBaseUrl("https://open.bigmodel.cn/api/paas/v4")).toBe(
      "zhipu",
    );
    expect(
      inferProviderFromBaseUrl("https://open.bigmodel.cn/api/coding/paas/v4"),
    ).toBe("zhipu_plan");
    expect(inferProviderFromBaseUrl("https://api.minimaxi.com/v1")).toBe(
      "minimax",
    );
  });

  it("falls back to custom", () => {
    expect(inferProviderFromBaseUrl("https://my-gateway.example/v1")).toBe("custom");
    expect(inferProviderFromBaseUrl("")).toBe("custom");
  });
});

describe("llmProviderLabel", () => {
  it("returns vendor label for title", () => {
    expect(llmProviderLabel("bailian")).toBe("百炼 / 通义");
    expect(llmProviderLabel("zhipu_plan")).toBe("智谱 Plan");
    expect(llmProviderLabel("minimax")).toBe("MiniMax");
    expect(llmProviderLabel("minimax_plan")).toBe("MiniMax Plan");
    expect(llmProviderLabel("openrouter")).toBe("OpenRouter");
    expect(llmProviderLabel("custom")).toBe("自定义");
  });
});

describe("resolvedLlmProviderLabel", () => {
  it("prefers a custom vendor name", () => {
    expect(resolvedLlmProviderLabel("custom", "家里网关")).toBe("家里网关");
    expect(resolvedLlmProviderLabel("deepseek", "  ")).toBe("DeepSeek");
    expect(resolvedLlmProviderLabel("", "")).toBe("自定义");
  });
});

describe("formatVendorModelTitle", () => {
  it("joins vendor and model", () => {
    expect(formatVendorModelTitle("自定义", "glm-5.3-flash")).toBe(
      "自定义 · glm-5.3-flash",
    );
    expect(formatVendorModelTitle("DeepSeek", "")).toBe("DeepSeek");
    expect(formatVendorModelTitle("", "glm")).toBe("glm");
  });
});

describe("inferEmbedProviderFromBaseUrl", () => {
  it("matches siliconflow and bailian", () => {
    expect(inferEmbedProviderFromBaseUrl("https://api.siliconflow.cn/v1")).toBe(
      "siliconflow",
    );
    expect(inferEmbedProviderFromBaseUrl("https://openrouter.ai/api/v1")).toBe(
      "openrouter",
    );
    expect(
      inferEmbedProviderFromBaseUrl(
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
      ),
    ).toBe("bailian");
  });
});

describe("embedProviderLabel", () => {
  it("returns Chinese labels", () => {
    expect(embedProviderLabel("siliconflow")).toBe("硅基流动");
    expect(embedProviderLabel("openrouter")).toBe("OpenRouter");
    expect(embedProviderLabel("bailian")).toBe("百炼");
  });
});
