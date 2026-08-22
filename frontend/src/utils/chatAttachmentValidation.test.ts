import { describe, expect, it } from "vitest";
import type { PendingFile } from "../types/composer";
import { MAX_VIDEO_UPLOAD_BYTES } from "./kbVideoUrls";
import { validatePendingAttachments } from "./chatAttachmentValidation";

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
        1,
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
        2,
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
});
