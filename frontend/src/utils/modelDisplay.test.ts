import { afterEach, describe, expect, it } from "vitest";
import { applyModelSettings, displayModelName } from "./modelDisplay";

afterEach(() => {
  applyModelSettings({});
});

describe("displayModelName", () => {
  it("returns recorded vendor · model as-is", () => {
    applyModelSettings({
      chat_models: [
        { model: "glm-5.3-flash", provider: "custom", provider_label: "家里网关" },
      ],
    });
    expect(displayModelName("家里网关 · glm-5.3-flash - max")).toBe(
      "家里网关 · glm-5.3-flash - max",
    );
  });

  it("prefixes old bare model names from the custom vendor label", () => {
    applyModelSettings({
      chat_models: [
        { model: "glm-5.3-flash", provider: "custom", provider_label: "家里网关" },
      ],
    });
    expect(displayModelName("glm-5.3-flash")).toBe("家里网关 · glm-5.3-flash");
    expect(displayModelName("glm-5.3-flash - max")).toBe(
      "家里网关 · glm-5.3-flash - max",
    );
  });

  it("falls back to the preset vendor when label is empty", () => {
    applyModelSettings({
      chat_models: [{ model: "deepseek-flash", provider: "deepseek" }],
    });
    expect(displayModelName("deepseek-flash")).toBe("DeepSeek · deepseek-flash");
  });

  it("returns the raw name when unmapped", () => {
    applyModelSettings({ chat_models: [] });
    expect(displayModelName("orphan-model")).toBe("orphan-model");
    expect(displayModelName("")).toBe("");
  });
});
