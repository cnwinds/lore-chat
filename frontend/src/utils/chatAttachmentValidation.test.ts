import { describe, expect, it } from "vitest";
import type { PendingFile } from "../types/composer";
import {
  MAX_VIDEO_DATA_WIRE_BYTES,
  MAX_VIDEO_UPLOAD_BYTES,
} from "./kbVideoUrls";
import {
  buildComposerMediaHints,
  validatePendingAttachments,
} from "./chatAttachmentValidation";

function pending(name: string, type: string, size: number): PendingFile {
  return {
    id: name,
    name,
    size,
    file: new File([new Uint8Array(Math.min(size, 4))], name, { type }),
  };
}

describe("validatePendingAttachments", () => {
  it("allows one video under size limit", () => {
    expect(
      validatePendingAttachments([pending("a.mp4", "video/mp4", 1024)]),
    ).toBeNull();
  });

  it("rejects multiple videos", () => {
    expect(
      validatePendingAttachments(
        [
          pending("a.mp4", "video/mp4", 1024),
          pending("b.mp4", "video/mp4", 1024),
        ],
        { maxVideos: 1 },
      ),
    ).toContain("1");
  });

  it("respects chain max_videos", () => {
    expect(
      validatePendingAttachments(
        [
          pending("a.mp4", "video/mp4", 1024),
          pending("b.mp4", "video/mp4", 1024),
        ],
        { maxVideos: 2 },
      ),
    ).toBeNull();
  });

  it("rejects oversized video", () => {
    expect(
      validatePendingAttachments([
        pending("big.mp4", "video/mp4", MAX_VIDEO_UPLOAD_BYTES + 1),
      ]),
    ).toContain("50MB");
  });

  it("rejects too many vision images", () => {
    expect(
      validatePendingAttachments(
        [
          pending("a.png", "image/png", 1024),
          pending("b.jpg", "image/jpeg", 1024),
        ],
        { maxImages: 1 },
      ),
    ).toContain("1");
  });
});

describe("buildComposerMediaHints", () => {
  const caps = {
    videoSupported: true,
    maxVideos: 1,
    imageSupported: false,
    maxImages: null,
    videoWireData: true,
  } as const;

  it("shows no limit hint for a single video within size cap", () => {
    const hints = buildComposerMediaHints(
      [pending("a.mp4", "video/mp4", 1024)],
      caps,
    );
    expect(hints).toEqual([]);
  });

  it("tips when video count exceeds chain max", () => {
    const hints = buildComposerMediaHints(
      [
        pending("a.mp4", "video/mp4", 1024),
        pending("b.mp4", "video/mp4", 1024),
      ],
      caps,
    );
    expect(hints).toContain("每条消息最多发送 1 个视频");
  });

  it("tips when a video exceeds upload size", () => {
    const hints = buildComposerMediaHints(
      [pending("big.mp4", "video/mp4", MAX_VIDEO_UPLOAD_BYTES + 1)],
      caps,
    );
    expect(hints.some((h) => h.includes("50MB"))).toBe(true);
  });

  it("includes signed-url hint for large data-wire videos", () => {
    const hints = buildComposerMediaHints(
      [pending("big.mp4", "video/mp4", MAX_VIDEO_DATA_WIRE_BYTES + 1)],
      {
        videoSupported: true,
        maxVideos: 2,
        imageSupported: false,
        maxImages: null,
        videoWireData: true,
      },
    );
    expect(hints.some((h) => h.includes("2 个"))).toBe(false);
    expect(hints.some((h) => h.includes("public_base_url"))).toBe(true);
  });

  it("warns when chain lacks video capability", () => {
    const hints = buildComposerMediaHints(
      [pending("a.mp4", "video/mp4", 1024)],
      {
        videoSupported: false,
        maxVideos: 1,
        imageSupported: false,
        maxImages: null,
        videoWireData: false,
      },
    );
    expect(hints[0]).toContain("未配置视频能力");
  });
});
