import { useCallback, useState } from "react";
import { ImageLightbox } from "../components/ImageLightbox";

export type ImagePreviewTarget = {
  src: string;
  alt: string;
  /** 可选：灯箱内提供下载 */
  downloadHref?: string;
};

/** 共享灯箱状态，避免各处重复 `{ src, alt }` + ImageLightbox 样板。 */
export function useImageLightbox() {
  const [preview, setPreview] = useState<ImagePreviewTarget | null>(null);

  const openPreview = useCallback((target: ImagePreviewTarget) => {
    setPreview(target);
  }, []);

  const closePreview = useCallback(() => {
    setPreview(null);
  }, []);

  const lightbox = (
    <ImageLightbox
      src={preview?.src ?? ""}
      alt={preview?.alt}
      downloadHref={preview?.downloadHref}
      open={!!preview}
      onClose={closePreview}
    />
  );

  return { openPreview, closePreview, lightbox };
}
