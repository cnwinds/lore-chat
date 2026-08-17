import { describe, expect, it } from "vitest";
import {
  draftChainNeedsSetup,
  isDraftApiKeyConfigured,
  mergeSettingsAttention,
  priceRowNeedsSetup,
} from "./settingsAttention";

describe("isDraftApiKeyConfigured", () => {
  it("rejects placeholders", () => {
    expect(isDraftApiKeyConfigured("sk-none")).toBe(false);
    expect(isDraftApiKeyConfigured("sk-your-key")).toBe(false);
    expect(isDraftApiKeyConfigured("")).toBe(false);
  });

  it("accepts real key or saved mask", () => {
    expect(isDraftApiKeyConfigured("sk-real-key")).toBe(true);
    expect(isDraftApiKeyConfigured("", "sk***xxxx")).toBe(true);
  });
});

describe("draftChainNeedsSetup", () => {
  it("flags empty chain", () => {
    expect(draftChainNeedsSetup([])).toBe(true);
  });

  it("flags placeholder key as unconfigured", () => {
    expect(
      draftChainNeedsSetup([
        {
          model: "gpt-4o",
          base_url: "https://api.openai.com/v1",
          api_key: "sk-none",
        },
      ]),
    ).toBe(true);
  });

  it("accepts masked saved key", () => {
    expect(
      draftChainNeedsSetup([
        {
          model: "gpt-4o",
          base_url: "https://api.openai.com/v1",
          api_key: "",
          api_key_masked: "sk***xxxx",
        },
      ]),
    ).toBe(false);
  });
});

describe("priceRowNeedsSetup", () => {
  it("requires chat input/output", () => {
    expect(
      priceRowNeedsSetup({
        model: "gpt-4o",
        kinds: ["chat"],
        prompt_per_1m: null,
        completion_per_1m: 1,
        embed_per_1m: null,
      }),
    ).toBe(true);
  });

  it("requires embed price", () => {
    expect(
      priceRowNeedsSetup({
        model: "text-embedding-3-small",
        kinds: ["embed"],
        prompt_per_1m: null,
        completion_per_1m: null,
        embed_per_1m: null,
      }),
    ).toBe(true);
  });
});

describe("mergeSettingsAttention", () => {
  const server = {
    any: true,
    model: { any: true, chat: true, utility: false, embed: false },
    memory: { any: true, pending_count: 2 },
    usage: { any: false, incomplete_price_count: 0 },
  };

  it("overrides model from draft overlay", () => {
    const merged = mergeSettingsAttention(server, {
      model: { chat: false, utility: false, embed: false },
    });
    expect(merged.model.any).toBe(false);
    expect(merged.memory.pending_count).toBe(2);
    expect(merged.any).toBe(true);
  });

  it("overrides usage incomplete count", () => {
    const merged = mergeSettingsAttention(server, { usageIncomplete: 3 });
    expect(merged.usage.any).toBe(true);
    expect(merged.usage.incomplete_price_count).toBe(3);
  });
});
