import { describe, expect, it } from "vitest";
import {
  draftCandidateHasContent,
  hydrateSettingsDrafts,
  parseImageProviders,
  parseSearchProviders,
  toSettingsPatch,
} from "./settingsDrafts";
import { emptyCandidate } from "./providerPresets";

describe("parseSearchProviders", () => {
  it("keeps one row per provider", () => {
    const rows = parseSearchProviders([
      { id: "tavily", provider: "tavily", api_key: "a" },
      { id: "t2", provider: "tavily", api_key: "b" },
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0].provider).toBe("tavily");
    expect(rows[0].api_key_masked).toMatch(/\*\*\*/);
  });
});

describe("parseImageProviders", () => {
  it("allows same vendor with different ids", () => {
    const rows = parseImageProviders([
      {
        id: "openai",
        provider: "openai",
        api_key: "a",
        base_url: "https://a",
        model: "dall-e-3",
      },
      {
        id: "openai-2",
        provider: "openai",
        api_key: "b",
        base_url: "https://b",
        model: "gpt-image-1",
      },
    ]);
    expect(rows).toHaveLength(2);
    expect(rows.map((r) => r.id).sort()).toEqual(["openai", "openai-2"]);
  });
});

describe("hydrateSettingsDrafts", () => {
  it("uses fallback public base url without mutating input", () => {
    const d = hydrateSettingsDrafts(
      { kb_path: "/kb", chat_models: [], utility_models: [], embed_models: [] },
      { fallbackPublicBaseUrl: "https://app.example" },
    );
    expect(d.kbPath).toBe("/kb");
    expect(d.publicBaseUrl).toBe("https://app.example");
    expect(d.publicBaseUrlFromFallback).toBe(true);
    expect(d.minVectorScore).toBe(0.45);
    expect(d.sandboxMirrorRegion).toBe("cn");
  });

  it("prefers saved public_base_url", () => {
    const d = hydrateSettingsDrafts(
      { public_base_url: "https://saved.example/" },
      { fallbackPublicBaseUrl: "https://app.example" },
    );
    expect(d.publicBaseUrl).toBe("https://saved.example/");
    expect(d.publicBaseUrlFromFallback).toBe(false);
  });
});

describe("toSettingsPatch", () => {
  it("drops empty model candidates and serializes chains", () => {
    const filled = {
      ...emptyCandidate(),
      id: "c1",
      model: "m1",
      base_url: "https://x",
      api_key: "sk-real",
      provider: "custom" as const,
      image: true,
      thinking: true,
      effort: "high",
      effort_options: ["low", "high"],
      image_wire: "url" as const,
    };
    const patch = toSettingsPatch({
      publicBaseUrl: "https://host",
      chatModels: [filled, emptyCandidate()],
      utilityModels: [],
      embedModels: [],
      searchProviders: [{ id: "tavily", provider: "tavily", api_key: "tv" }],
      imageProviders: [
        {
          id: "openai",
          provider: "openai",
          api_key: "",
          base_url: "https://api.openai.com/v1",
          model: "dall-e-3",
        },
      ],
      minVectorScore: 0.5,
      rrfK: 60,
      laneCandidateK: 20,
      agentMaxToolCalls: 10,
      agentParallelTools: false,
      agentMaxParallel: 2,
      sandboxTrustMode: true,
      sandboxMirrorRegion: "global",
    });
    expect(patch.public_base_url).toBe("https://host");
    expect(patch.chat_models).toHaveLength(1);
    expect((patch.chat_models as unknown[])[0]).toMatchObject({
      id: "c1",
      model: "m1",
      api_key: "sk-real",
      image_wire: "url",
    });
    expect(patch.sandbox_mirror_region).toBe("global");
    expect(patch.agent_parallel_tools).toBe(false);
  });
});

describe("draftCandidateHasContent", () => {
  it("treats blank leftover as empty", () => {
    expect(draftCandidateHasContent(emptyCandidate())).toBe(false);
    expect(draftCandidateHasContent({ model: "x" })).toBe(true);
  });
});
