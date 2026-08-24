import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { KbAttachmentList } from "./KbAttachmentList";

vi.mock("../api", () => ({
  downloadUrl: (path: string) => `/api/download?path=${encodeURIComponent(path)}`,
}));

vi.mock("../hooks/useImageLightbox", () => ({
  useImageLightbox: () => ({ openPreview: vi.fn(), lightbox: null }),
}));

vi.mock("../hooks/useVideoLightbox", () => ({
  useVideoLightbox: () => ({ openPreview: vi.fn(), lightbox: null }),
}));

describe("KbAttachmentList", () => {
  it("renders video attachments with thumb button", () => {
    const { container } = render(
      <KbAttachmentList paths={["媒体/上传/2026-01/demo.mp4"]} />,
    );
    const btn = container.querySelector(".kb-attachment-video-btn");
    expect(btn).not.toBeNull();
    const video = container.querySelector("video.kb-attachment-video");
    expect(video).not.toBeNull();
    expect(video?.getAttribute("preload")).toBe("metadata");
    expect(video?.getAttribute("src")).toContain("demo.mp4");
  });

  it("renders download link for non-media files", () => {
    const { getByText } = render(<KbAttachmentList paths={["docs/readme.txt"]} />);
    expect(getByText(/下载附件/)).toBeTruthy();
  });

  it("uses media grant URLs as-is for image thumbs", () => {
    const grant = "https://share.example.com/api/media/grant/abcdefghijklmnopqr";
    const { container } = render(<KbAttachmentList paths={[grant]} />);
    const img = container.querySelector("img");
    expect(img?.getAttribute("src")).toBe(grant);
  });
});
