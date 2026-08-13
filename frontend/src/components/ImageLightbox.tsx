import { useEffect } from "react";
import { createPortal } from "react-dom";

type Props = {
  src: string;
  alt?: string;
  open: boolean;
  onClose: () => void;
  /** 有则在灯箱底部提供下载 */
  downloadHref?: string;
};

/** 全屏看大图：点遮罩 / × / Esc 关闭。 */
export function ImageLightbox({
  src,
  alt = "",
  open,
  onClose,
  downloadHref,
}: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      className="image-lightbox"
      role="dialog"
      aria-modal="true"
      aria-label={alt || "图片预览"}
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
      <img
        src={src}
        alt={alt}
        className="image-lightbox-img"
        draggable={false}
        onClick={(e) => e.stopPropagation()}
      />
      {downloadHref ? (
        <a
          className="image-lightbox-download"
          href={downloadHref}
          download
          onClick={(e) => e.stopPropagation()}
        >
          下载原图
        </a>
      ) : null}
    </div>,
    document.body,
  );
}
