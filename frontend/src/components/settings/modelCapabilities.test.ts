import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("../../api", () => ({
  lookupModelCapabilities: vi.fn(),
}));

import { lookupModelCapabilities } from "../../api";
import {
  capsFromLookupResponse,
  conservativeModelCaps,
  resolveModelCaps,
} from "./modelCapabilities";

const lookupMock = vi.mocked(lookupModelCapabilities);

describe("conservativeModelCaps", () => {
  it("uses non-thinking defaults", () => {
    expect(conservativeModelCaps()).toEqual({
      image: false,
      thinking: false,
      effort: "medium",
      effort_options: [],
      image_wire: "data",
      thinking_protocol: "none",
    });
  });
});

describe("capsFromLookupResponse", () => {
  it("maps wire fields", () => {
    expect(
      capsFromLookupResponse({
        ok: true,
        model: "agnes-2.5-flash",
        image: true,
        thinking: true,
        effort: "medium",
        effort_options: [],
        image_wire: "url",
        thinking_protocol: "agnes",
        source: "prefix",
      }),
    ).toEqual({
      image: true,
      thinking: true,
      effort: "medium",
      effort_options: [],
      image_wire: "url",
      thinking_protocol: "agnes",
    });
  });
});

describe("resolveModelCaps", () => {
  beforeEach(() => {
    lookupMock.mockReset();
  });

  it("returns conservative caps when lookup fails", async () => {
    lookupMock.mockRejectedValueOnce(new Error("network"));
    await expect(resolveModelCaps("glm-5.3")).resolves.toEqual(
      conservativeModelCaps(),
    );
  });

  it("returns lookup payload on success", async () => {
    lookupMock.mockResolvedValueOnce({
      ok: true,
      model: "glm-5.3",
      image: false,
      thinking: true,
      effort: "medium",
      effort_options: ["low", "medium", "high", "max"],
      image_wire: "data",
      thinking_protocol: "qwen",
      source: "prefix",
    });
    const caps = await resolveModelCaps("glm-5.3", "https://example.com");
    expect(lookupMock).toHaveBeenCalledWith("glm-5.3", "https://example.com");
    expect(caps.thinking).toBe(true);
    expect(caps.effort_options).toEqual(["low", "medium", "high", "max"]);
  });
});
