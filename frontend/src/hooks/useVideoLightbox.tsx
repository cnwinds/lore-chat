import { useCallback, useState } from "react";
import { VideoLightbox } from "../components/VideoLightbox";

export type VideoPreviewTarget = {
  src: string;
  title: string;
  downloadHref?: string;
};

/** 共享视频灯箱状态（媒体图库、附件预览等）。 */
export function useVideoLightbox() {
  const [preview, setPreview] = useState<VideoPreviewTarget | null>(null);

  const openPreview = useCallback((target: VideoPreviewTarget) => {
    setPreview(target);
  }, []);

  const closePreview = useCallback(() => {
    setPreview(null);
  }, []);

  const lightbox = (
    <VideoLightbox
      src={preview?.src ?? ""}
      title={preview?.title}
      downloadHref={preview?.downloadHref}
      open={!!preview}
      onClose={closePreview}
    />
  );

  return { openPreview, closePreview, lightbox };
}
