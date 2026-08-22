import { describe, expect, it } from "vitest";
import {
  aggregateChainMediaCaps,
  mergeCandidateMediaCaps,
} from "./chatChainMedia";

describe("chatChainMedia", () => {
  it("merges saved caps over catalog defaults", () => {
    expect(
      mergeCandidateMediaCaps(
        { video: true, max_videos: 2 },
        {
          video: false,
          max_videos: 1,
          image: false,
          max_images: null,
          video_wire: "data",
        },
      ),
    ).toEqual({
      image: false,
      maxImages: null,
      video: true,
      maxVideos: 2,
      videoWire: "data",
    });
    expect(
      mergeCandidateMediaCaps(
        {},
        {
          video: true,
          max_videos: 3,
          image: true,
          max_images: 5,
          video_wire: "url",
        },
      ),
    ).toEqual({
      image: true,
      maxImages: 5,
      video: true,
      maxVideos: 3,
      videoWire: "url",
    });
  });

  it("aggregates chain caps conservatively", () => {
    expect(
      aggregateChainMediaCaps([
        {
          image: true,
          maxImages: 5,
          video: true,
          maxVideos: 3,
          videoWire: "data",
        },
        {
          image: true,
          maxImages: 2,
          video: true,
          maxVideos: 1,
          videoWire: "url",
        },
      ]),
    ).toEqual({
      videoSupported: true,
      maxVideos: 1,
      imageSupported: true,
      maxImages: 2,
      videoWireData: true,
    });
  });

  it("returns no image cap when chain has no image candidates", () => {
    expect(
      aggregateChainMediaCaps([
        {
          image: false,
          maxImages: null,
          video: false,
          maxVideos: 1,
          videoWire: "data",
        },
      ]),
    ).toEqual({
      videoSupported: false,
      maxVideos: 1,
      imageSupported: false,
      maxImages: null,
      videoWireData: false,
    });
  });
});
