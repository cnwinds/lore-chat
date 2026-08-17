import { describe, expect, it } from "vitest";
import { providerApiKeyUrl } from "./providerApiKeyUrls";

describe("providerApiKeyUrl", () => {
  it("returns console URLs for known presets", () => {
    expect(providerApiKeyUrl("openai")).toContain("openai.com");
    expect(providerApiKeyUrl("zhipu")).toContain("bigmodel.cn");
    expect(providerApiKeyUrl("bailian")).toContain("aliyun.com");
    expect(providerApiKeyUrl("deepseek")).toContain("deepseek.com");
    expect(providerApiKeyUrl("agnes")).toContain("agnes-ai.com");
    expect(providerApiKeyUrl("siliconflow")).toContain("siliconflow");
    expect(providerApiKeyUrl("tavily")).toContain("tavily");
    expect(providerApiKeyUrl("serper")).toContain("serper");
    expect(providerApiKeyUrl("brave")).toContain("brave.com");
  });

  it("returns null for custom / empty / unknown", () => {
    expect(providerApiKeyUrl("custom")).toBeNull();
    expect(providerApiKeyUrl("")).toBeNull();
    expect(providerApiKeyUrl("unknown-vendor")).toBeNull();
  });
});
