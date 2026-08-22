import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

type Props = {
  src: string;
  title?: string;
  open: boolean;
  onClose: () => void;
  downloadHref?: string;
};

/** 全屏看视频：点遮罩 / × / Esc 关闭。 */
export function VideoLightbox({
  src,
  title = "",
  open,
  onClose,
  downloadHref,
}: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) {
      const el = videoRef.current;
      if (el) {
        el.pause();
        el.currentTime = 0;
      }
    }
  }, [open]);

  if (!open) return null;

  return createPortal(
    <div
      className="image-lightbox video-lightbox"
      role="dialog"
      aria-modal="true"
      aria-label={title || "视频预览"}
      onClick={onClose}
    >
      <button
        type="button"
        className="image-lightbox-close"
        onClick={onClose}
        aria-label="关闭"
      >
        ×
      </button>
      <video
        ref={videoRef}
        src={src}
        className="video-lightbox-player"
        controls
        playsInline
        autoPlay
        onClick={(e) => e.stopPropagation()}
      />
      {downloadHref ? (
        <a
          className="image-lightbox-download"
          href={downloadHref}
          download
          onClick={(e) => e.stopPropagation()}
        >
          下载视频
        </a>
      ) : null}
    </div>,
    document.body,
  );
}
