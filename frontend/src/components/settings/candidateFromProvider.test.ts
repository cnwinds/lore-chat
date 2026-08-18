import { describe, expect, it } from "vitest";
import {
  EMBED_PROVIDER_DEFAULT_BASE_URL,
  LLM_PROVIDER_DEFAULT_BASE_URL,
  candidateFromProvider,
  embedCandidateFromProvider,
  embedProviderLabel,
  inferEmbedProviderFromBaseUrl,
  inferProviderFromBaseUrl,
  llmProviderLabel,
} from "./providerPresets";
import { inferCapsFromModel, supportedEfforts } from "./ModelSettingsTab";

describe("candidateFromProvider", () => {
  it("leaves custom preset empty for user to fill", () => {
    const c = candidateFromProvider("custom");
    expect(c.provider).toBe("custom");
    expect(c.base_url).toBe("");
    expect(c.model).toBe("");
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
  });

  it("falls back to custom", () => {
    expect(inferProviderFromBaseUrl("https://my-gateway.example/v1")).toBe("custom");
    expect(inferProviderFromBaseUrl("")).toBe("custom");
  });
});

describe("llmProviderLabel", () => {
  it("returns vendor label for title", () => {
    expect(llmProviderLabel("bailian")).toBe("百炼 / 通义");
    expect(llmProviderLabel("openrouter")).toBe("OpenRouter");
    expect(llmProviderLabel("custom")).toBe("自定义");
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

describe("inferCapsFromModel", () => {
  it("marks glm as thinking with max effort options", () => {
    const caps = inferCapsFromModel("glm-5.3");
    expect(caps.thinking).toBe(true);
    expect(caps.effort_options).toEqual(["low", "medium", "high", "max"]);
  });

  it("keeps unknown models without max", () => {
    expect(supportedEfforts("totally-unknown-xyz")).toEqual([
      "low",
      "medium",
      "high",
    ]);
  });

  it("reads OpenRouter-style vendor/model ids", () => {
    expect(inferCapsFromModel("deepseek/deepseek-v4-pro").thinking_protocol).toBe(
      "deepseek",
    );
    expect(inferCapsFromModel("openai/gpt-5.2").thinking_protocol).toBe(
      "openai_kwargs",
    );
    expect(supportedEfforts("openai/gpt-5.2")).toEqual([
      "none",
      "low",
      "medium",
      "high",
      "xhigh",
    ]);
  });
});
