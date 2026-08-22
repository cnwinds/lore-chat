import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../components/settings/modelCapabilities", () => ({
  resolveModelCaps: vi.fn(),
}));

import { resolveModelCaps } from "../components/settings/modelCapabilities";
import { resolveChainMediaCapsFromSettings } from "./chatChainMedia";

const resolveMock = vi.mocked(resolveModelCaps);

describe("resolveChainMediaCapsFromSettings", () => {
  beforeEach(() => {
    resolveMock.mockReset();
  });

  it("merges catalog lookup with saved chain fields", async () => {
    resolveMock.mockResolvedValue({
      image: true,
      video: true,
      thinking: false,
      effort: "medium",
      effort_options: [],
      image_wire: "data",
      video_wire: "data",
      max_videos: 3,
      max_images: null,
      thinking_protocol: "none",
    });
    const caps = await resolveChainMediaCapsFromSettings([
      { model: "stealth/ox-alpha", video: true, max_videos: 2 },
    ]);
    expect(resolveMock).toHaveBeenCalledWith(
      "stealth/ox-alpha",
      undefined,
    );
    expect(caps).toEqual({ videoSupported: true, maxVideos: 2 });
  });

  it("returns conservative defaults for empty chain", async () => {
    const caps = await resolveChainMediaCapsFromSettings([]);
    expect(caps).toEqual({ videoSupported: false, maxVideos: 1 });
    expect(resolveMock).not.toHaveBeenCalled();
  });
});
