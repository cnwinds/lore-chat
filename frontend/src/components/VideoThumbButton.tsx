import type { VideoPreviewTarget } from "../hooks/useVideoLightbox";

type Props = {
  src: string;
  title: string;
  className?: string;
  videoClassName?: string;
  downloadHref?: string;
  onOpen: (target: VideoPreviewTarget) => void;
  onRemove?: () => void;
};

/** 可点击视频缩略图：点开共享视频灯箱播放。 */
export function VideoThumbButton({
  src,
  title,
  className = "media-gallery-tile-video-btn",
  videoClassName = "media-gallery-tile-video",
  downloadHref,
  onOpen,
  onRemove,
}: Props) {
  const open = () => onOpen({ src, title, downloadHref });

  return (
    <div
      className={className}
      role="button"
      tabIndex={0}
      title={`${title}（点击播放）`}
      onClick={open}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
      }}
    >
      <video
        src={src}
        className={videoClassName}
        muted
        playsInline
        preload="metadata"
        draggable={false}
      />
      <span className="video-thumb-play-icon" aria-hidden>▶</span>
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
