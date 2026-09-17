import { describe, expect, it } from "vitest";
import { parseCandidates } from "./modelChainDrafts";

describe("parseCandidates", () => {
  it("keeps a custom vendor label", () => {
    const rows = parseCandidates([
      {
        id: "c1",
        model: "glm-5.3-flash",
        provider: "custom",
        provider_label: "家里网关",
        base_url: "https://x",
      },
    ]);
    expect(rows[0].provider_label).toBe("家里网关");
  });

  it("defaults an absent vendor label to empty", () => {
    const rows = parseCandidates([
      { model: "deepseek-flash", provider: "deepseek", base_url: "https://api.deepseek.com" },
    ]);
    expect(rows[0].provider_label).toBe("");
    expect(rows[0].provider).toBe("deepseek");
  });
});
