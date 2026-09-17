import { describe, expect, it } from "vitest";
import {
  clampWebSearchDefaultK,
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

  it("reads a saved vendor label", () => {
    const rows = parseImageProviders([
      {
        id: "openai",
        provider: "openai",
        api_key: "a",
        model: "dall-e-3",
        provider_label: "我家 OpenAI",
      },
    ]);
    expect(rows[0].provider_label).toBe("我家 OpenAI");
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
    expect(d.sandboxMaxRoles).toBe(4);
    expect(d.sandboxIdleTtlSec).toBe(3600);
    expect(d.sandboxDestroyVolumeOnRoleDelete).toBe(false);
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
      provider_label: "家里网关",
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
          provider_label: "",
        },
      ],
      minVectorScore: 0.5,
      rrfK: 60,
      laneCandidateK: 20,
      webSearchDefaultK: 7,
      agentMaxToolCalls: 10,
      agentParallelTools: false,
      agentMaxParallel: 2,
      sandboxTrustMode: true,
      sandboxMirrorRegion: "global",
      sandboxMaxRoles: 6,
      sandboxIdleTtlSec: 1800,
      sandboxDestroyVolumeOnRoleDelete: true,
      continuityIdleHours: 6,
    });
    expect(patch.public_base_url).toBe("https://host");
    expect(patch.chat_models).toHaveLength(1);
    expect((patch.chat_models as unknown[])[0]).toMatchObject({
      id: "c1",
      model: "m1",
      api_key: "sk-real",
      image_wire: "url",
      provider_label: "家里网关",
    });
    expect(patch.sandbox_mirror_region).toBe("global");
    expect(patch.sandbox_max_roles).toBe(6);
    expect(patch.sandbox_idle_ttl_sec).toBe(1800);
    expect(patch.sandbox_destroy_volume_on_role_delete).toBe(true);
    expect(patch.web_search_default_k).toBe(7);
    expect(patch.agent_parallel_tools).toBe(false);
    expect((patch.image_providers as unknown[])[0]).toMatchObject({
      id: "openai",
      provider_label: "OpenAI Images",
    });
  });
});

describe("draftCandidateHasContent", () => {
  it("treats blank leftover as empty", () => {
    expect(draftCandidateHasContent(emptyCandidate())).toBe(false);
    expect(draftCandidateHasContent({ model: "x" })).toBe(true);
  });
});

describe("clampWebSearchDefaultK", () => {
  it("clamps to 1–20 and rounds", () => {
    expect(clampWebSearchDefaultK(0)).toBe(1);
    expect(clampWebSearchDefaultK(21)).toBe(20);
    expect(clampWebSearchDefaultK(7.6)).toBe(8);
    expect(clampWebSearchDefaultK(Number.NaN)).toBe(5);
  });
});
