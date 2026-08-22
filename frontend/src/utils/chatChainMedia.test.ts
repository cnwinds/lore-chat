import { describe, expect, it } from "vitest";
import {
  aggregateChainMediaCaps,
  chatChainMaxVideos,
  chatChainSupportsVideo,
  mergeCandidateMediaCaps,
} from "./chatChainMedia";

describe("chatChainMedia", () => {
  it("detects video capability on chain", () => {
    expect(
      chatChainSupportsVideo([
        { video: false },
        { video: true, max_videos: 2 },
      ]),
    ).toBe(true);
    expect(chatChainSupportsVideo([{ video: false }])).toBe(false);
  });

  it("uses minimum max_videos among video-capable candidates", () => {
    expect(
      chatChainMaxVideos([
        { video: true, max_videos: 3 },
        { video: true, max_videos: 1 },
      ]),
    ).toBe(1);
    expect(chatChainMaxVideos([])).toBe(1);
  });

  it("ignores max_videos from non-video candidates", () => {
    expect(
      chatChainMaxVideos([
        { video: false, max_videos: 5 },
        { video: true, max_videos: 2 },
      ]),
    ).toBe(2);
  });

  it("merges saved caps over catalog defaults", () => {
    expect(
      mergeCandidateMediaCaps(
        { video: true, max_videos: 2 },
        { video: false, max_videos: 1 },
      ),
    ).toEqual({ video: true, maxVideos: 2 });
    expect(
      mergeCandidateMediaCaps({}, { video: true, max_videos: 3 }),
    ).toEqual({ video: true, maxVideos: 3 });
  });

  it("aggregates chain caps conservatively", () => {
    expect(
      aggregateChainMediaCaps([
        { video: true, maxVideos: 3 },
        { video: true, maxVideos: 1 },
      ]),
    ).toEqual({ videoSupported: true, maxVideos: 1 });
  });
});
