import { fireEvent, render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MediaGalleryPanel } from "./MediaGalleryPanel";

vi.mock("../../api", () => ({
  downloadUrl: (path: string, opts?: { download?: boolean }) =>
    opts?.download
      ? `/api/download?path=${encodeURIComponent(path)}&download=1`
      : `/api/download?path=${encodeURIComponent(path)}`,
  getTree: vi.fn(),
}));

vi.mock("../../hooks/useImageLightbox", () => ({
  useImageLightbox: () => ({ openPreview: vi.fn(), lightbox: null }),
}));

describe("MediaGalleryPanel", () => {
  it("shows video tiles in grid and opens video lightbox on click", async () => {
    const { container, getByRole } = render(
      <MediaGalleryPanel
        directory="媒体/上传/2026-08"
        paths={[
          "媒体/上传/2026-08/photo.png",
          "媒体/上传/2026-08/clip.mp4",
          "媒体/上传/2026-08/readme.txt",
        ]}
        onClose={() => {}}
      />,
    );

    await waitFor(() => {
      expect(container.textContent).toContain("1 张图片");
      expect(container.textContent).toContain("1 个视频");
    });

    const thumb = container.querySelector(".media-gallery-tile-video-btn");
    expect(thumb).not.toBeNull();
    fireEvent.click(thumb!);

    const dialog = getByRole("dialog", { name: "媒体/上传/2026-08/clip.mp4" });
    const player = dialog.querySelector("video.video-lightbox-player");
    expect(player).not.toBeNull();
    expect(player?.getAttribute("src")).toContain("clip.mp4");
    expect(player?.hasAttribute("controls")).toBe(true);
  });
});
