import type { ImagePreviewTarget } from "../hooks/useImageLightbox";

type Props = {
  src: string;
  alt: string;
  title?: string;
  className?: string;
  imageClassName?: string;
  downloadHref?: string;
  onOpen: (target: ImagePreviewTarget) => void;
  onRemove?: () => void;
};

/** 可点击缩略图：打开共享灯箱；可选角标移除。 */
export function ImageThumbButton({
  src,
  alt,
  title,
  className = "composer-image-chip",
  imageClassName = "composer-image-thumb",
  downloadHref,
  onOpen,
  onRemove,
}: Props) {
  return (
    <div
      className={className}
      role="button"
      tabIndex={0}
      title={title ?? `${alt}（点击查看大图）`}
      onClick={() => onOpen({ src, alt, downloadHref })}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen({ src, alt, downloadHref });
        }
      }}
    >
      <img
        src={src}
        alt={alt}
        className={imageClassName}
        loading="lazy"
        draggable={false}
      />
      {onRemove && (
        <button
          type="button"
          className="composer-chip-close composer-image-chip-close"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          aria-label="移除"
        >
          ×
        </button>
      )}
    </div>
  );
}
