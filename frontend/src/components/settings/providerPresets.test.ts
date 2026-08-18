import { describe, expect, it } from "vitest";
import { embedCandidatesFromLegacy } from "./providerPresets";

describe("embedCandidatesFromLegacy", () => {
  it("returns empty when nothing configured", () => {
    expect(embedCandidatesFromLegacy({})).toEqual([]);
  });

  it("keeps a legacy row when model is set", () => {
    const rows = embedCandidatesFromLegacy({ embed_model: "text-embedding-v3" });
    expect(rows).toHaveLength(1);
    expect(rows[0].model).toBe("text-embedding-v3");
  });
});
