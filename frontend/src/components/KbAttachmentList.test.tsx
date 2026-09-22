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

  it("renders a file card with hover tip for non-media files", () => {
    const path =
      "媒体/2026-09/数据_设备角色列表_JPGQHc1OepVFXAUBBQqXt2oRWEBxWy2L20260922_105900.csv";
    const { container, queryByText } = render(<KbAttachmentList paths={[path]} />);
    const card = container.querySelector("a.kb-file-card");
    expect(card).not.toBeNull();
    expect(card?.getAttribute("href")).toContain(encodeURIComponent(path));
    expect(card?.getAttribute("aria-label")).toBe(
      "数据_设备角色列表_JPGQHc1OepVFXAUBBQqXt2oRWEBxWy2L20260922_105900.csv",
    );
    expect(card?.querySelector(".kb-file-card-name")?.textContent).toBe(
      "数据_设备角色列表_JPGQHc1OepVFXAUBBQqXt2oRWEBxWy2L20260922_105900.csv",
    );
    expect(card?.querySelector(".kb-file-card-ext")?.textContent).toBe("csv");
    const tip = card?.querySelector(".kb-file-card-tip");
    expect(tip?.getAttribute("role")).toBe("tooltip");
    expect(tip?.querySelector(".kb-file-card-tip-name")?.textContent).toBe(
      "数据_设备角色列表_JPGQHc1OepVFXAUBBQqXt2oRWEBxWy2L20260922_105900.csv",
    );
    expect(tip?.querySelector(".kb-file-card-tip-path")?.textContent).toBe(path);
    expect(queryByText(/下载附件/)).toBeNull();
  });

  it("omits the path line when the attachment is only a filename", () => {
    const { container } = render(<KbAttachmentList paths={["notes.md"]} />);
    const card = container.querySelector("a.kb-file-card");
    expect(card?.querySelector(".kb-file-card-tip-name")?.textContent).toBe("notes.md");
    expect(card?.querySelector(".kb-file-card-tip-path")).toBeNull();
    expect(card?.querySelector(".kb-file-card-ext")?.textContent).toBe("md");
  });

  it("uses media grant URLs as-is for image thumbs", () => {
    const grant = "https://share.example.com/api/media/grant/abcdefghijklmnopqr";
    const { container } = render(<KbAttachmentList paths={[grant]} />);
    const img = container.querySelector("img");
    expect(img?.getAttribute("src")).toBe(grant);
  });
});
