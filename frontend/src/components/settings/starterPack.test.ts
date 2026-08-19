import { describe, expect, it } from "vitest";
import {
  LLM_PROVIDER_DEFAULT_BASE_URL,
  emptyCandidate,
} from "./providerPresets";
import {
  STARTER_AGNES_MODEL,
  STARTER_EMBED_MODEL,
  applyFreeStarterPack,
  isStarterPackShape,
  readStarterPackKeys,
  starterChainVacant,
  starterPackCanSave,
  starterPackPhase,
  withStarterPackKeys,
  type StarterPackDrafts,
} from "./starterPack";

function emptyDrafts(): StarterPackDrafts {
  return { chat: [], utility: [], embed: [], search: [] };
}

describe("applyFreeStarterPack", () => {
  it("fills chat, utility, embed and tavily with inferred caps", () => {
    const next = applyFreeStarterPack(emptyDrafts());
    expect(next.chat).toHaveLength(1);
    expect(next.utility).toHaveLength(1);
    expect(next.embed).toHaveLength(1);
    expect(next.search).toHaveLength(1);
    expect(next.chat[0].model).toBe(STARTER_AGNES_MODEL);
    expect(next.chat[0].provider).toBe("agnes");
    expect(next.chat[0].base_url).toBe(LLM_PROVIDER_DEFAULT_BASE_URL.agnes);
    expect(next.chat[0].image).toBe(true);
    expect(next.chat[0].thinking).toBe(true);
    expect(next.chat[0].thinking_protocol).toBe("agnes");
    expect(next.chat[0].image_wire).toBe("url");
    expect(next.utility[0].model).toBe(STARTER_AGNES_MODEL);
    expect(next.chat[0].id).not.toBe(next.utility[0].id);
    expect(next.embed[0].model).toBe(STARTER_EMBED_MODEL);
    expect(next.embed[0].provider).toBe("siliconflow");
    expect(next.search[0].provider).toBe("tavily");
    expect(isStarterPackShape(next)).toBe(true);
  });

  it("does not duplicate existing tavily", () => {
    const next = applyFreeStarterPack({
      ...emptyDrafts(),
      search: [{ id: "keep-me", provider: "tavily", api_key: "tv-existing" }],
    });
    expect(next.search).toHaveLength(1);
    expect(next.search[0].id).toBe("keep-me");
    expect(next.search[0].api_key).toBe("tv-existing");
  });
});

describe("starterPackPhase", () => {
  it("offers when chains are empty", () => {
    expect(starterPackPhase(emptyDrafts(), false)).toBe("offer");
  });

  it("offers when leftover candidates have no model/url/key", () => {
    expect(
      starterPackPhase(
        {
          chat: [emptyCandidate()],
          utility: [emptyCandidate()],
          embed: [],
          search: [],
        },
        false,
      ),
    ).toBe("offer");
  });

  it("hides after dismiss even if empty", () => {
    expect(starterPackPhase(emptyDrafts(), true)).toBe("hidden");
  });

  it("collects keys after pack is applied", () => {
    const applied = applyFreeStarterPack(emptyDrafts());
    expect(starterPackPhase(applied, false)).toBe("collecting");
  });

  it("stays collecting while typed keys are not yet saved", () => {
    const applied = withStarterPackKeys(applyFreeStarterPack(emptyDrafts()), {
      agnes: "ak-real-key",
    });
    expect(starterPackCanSave(applied)).toBe(true);
    expect(starterPackPhase(applied, false)).toBe("collecting");
  });

  it("hides after pack keys have been persisted", () => {
    const applied = applyFreeStarterPack(emptyDrafts());
    applied.chat[0].api_key_masked = "ak***xxxx";
    applied.utility[0].api_key_masked = "ak***xxxx";
    expect(starterPackCanSave(applied)).toBe(true);
    expect(starterPackPhase(applied, false)).toBe("hidden");
  });

  it("hides when user already has other candidates", () => {
    expect(
      starterPackPhase(
        {
          chat: [
            {
              id: "x",
              model: "",
              base_url: "https://api.deepseek.com",
              api_key: "",
              provider: "deepseek",
              image: false,
              thinking: false,
              effort: "medium",
              effort_options: [],
              image_wire: "data",
              thinking_protocol: "none",
            },
          ],
          utility: [],
          embed: [],
          search: [],
        },
        false,
      ),
    ).toBe("hidden");
  });
});

describe("starterChainVacant", () => {
  it("treats blank leftover rows as vacant", () => {
    expect(starterChainVacant([emptyCandidate()])).toBe(true);
    expect(starterChainVacant([])).toBe(true);
  });

  it("treats a preset with base URL as occupied", () => {
    expect(
      starterChainVacant([
        { model: "", base_url: "https://api.deepseek.com", api_key: "" },
      ]),
    ).toBe(false);
  });
});

describe("withStarterPackKeys", () => {
  it("copies Agnes key to both chat and utility", () => {
    const next = withStarterPackKeys(applyFreeStarterPack(emptyDrafts()), {
      agnes: "ak-shared",
      siliconflow: "sk-sf",
      tavily: "tv-key",
    });
    expect(next.chat[0].api_key).toBe("ak-shared");
    expect(next.utility[0].api_key).toBe("ak-shared");
    expect(next.embed[0].api_key).toBe("sk-sf");
    expect(next.search[0].api_key).toBe("tv-key");
    const keys = readStarterPackKeys(next);
    expect(keys.agnes).toBe("ak-shared");
    expect(keys.siliconflow).toBe("sk-sf");
    expect(keys.tavily).toBe("tv-key");
  });

  it("does not allow save when utility key is missing", () => {
    const applied = applyFreeStarterPack(emptyDrafts());
    applied.chat[0].api_key = "ak-real-key";
    applied.utility[0].api_key = "";
    expect(starterPackCanSave(applied)).toBe(false);
  });
});
