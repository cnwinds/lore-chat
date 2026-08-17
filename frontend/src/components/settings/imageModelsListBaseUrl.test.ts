import { describe, expect, it } from "vitest";
import {
  IMAGE_PROVIDER_DEFAULT_BASE_URL,
  imageModelsListBaseUrl,
} from "./ImageProviderEditor";

describe("imageModelsListBaseUrl", () => {
  it("keeps openai/zhipu/agnes roots", () => {
    expect(imageModelsListBaseUrl("openai", "")).toBe(
      IMAGE_PROVIDER_DEFAULT_BASE_URL.openai,
    );
    expect(
      imageModelsListBaseUrl("zhipu", "https://open.bigmodel.cn/api/paas/v4/"),
    ).toBe("https://open.bigmodel.cn/api/paas/v4");
    expect(imageModelsListBaseUrl("agnes", "")).toBe(
      IMAGE_PROVIDER_DEFAULT_BASE_URL.agnes,
    );
  });

  it("maps bailian dashscope root to compatible-mode for /models", () => {
    expect(imageModelsListBaseUrl("bailian", "")).toBe(
      "https://dashscope.aliyuncs.com/compatible-mode/v1",
    );
    expect(
      imageModelsListBaseUrl("bailian", "https://dashscope.aliyuncs.com"),
    ).toBe("https://dashscope.aliyuncs.com/compatible-mode/v1");
    expect(
      imageModelsListBaseUrl(
        "bailian",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
      ),
    ).toBe("https://dashscope.aliyuncs.com/compatible-mode/v1");
  });

  it("uses typed base URL for custom with no preset fallback", () => {
    expect(imageModelsListBaseUrl("custom", "")).toBe("");
    expect(
      imageModelsListBaseUrl("custom", "https://gateway.example/v1/"),
    ).toBe("https://gateway.example/v1");
  });
});
