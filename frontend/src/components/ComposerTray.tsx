import { useEffect, useState } from "react";
import type { DocTrayItem, PendingFile } from "../types/composer";
import { isMarkdownPath } from "../utils/kbPath";
import { isImageFile } from "../utils/kbImageUrls";
import { isVideoFile } from "../utils/kbVideoUrls";
import { ImageThumbButton } from "./ImageThumbButton";
import { VideoThumbButton } from "./VideoThumbButton";
import { useImageLightbox } from "../hooks/useImageLightbox";
import { useVideoLightbox } from "../hooks/useVideoLightbox";
import type { VideoPreviewTarget } from "../hooks/useVideoLightbox";

type Props = {
  items: DocTrayItem[];
  primaryPath: string | null;
  pendingFiles: PendingFile[];
  mediaCapabilityHints?: string[];
  onSetPrimary: (path: string) => void;
  onRemoveDoc: (path: string) => void;
  onRemoveFile: (id: string) => void;
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

type DocChipProps = {
  title: string;
  tooltip?: string;
  primary?: boolean;
  onClick?: () => void;
  onRemove?: () => void;
};

export function DocChip({ title, tooltip, primary, onClick, onRemove }: DocChipProps) {
  return (
    <div
      className={`composer-doc-chip${primary ? " composer-doc-chip--primary" : ""}`}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      title={tooltip ?? title}
    >
      <span className="composer-doc-chip-bar" aria-hidden />
      <span className="composer-doc-chip-title">{title}</span>
      {onRemove && (
        <button
          type="button"
          className="composer-chip-close"
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

type FileChipProps = {
  name: string;
  tooltip?: string;
  size?: number;
  onRemove?: () => void;
};

export function FileChip({ name, tooltip, size, onRemove }: FileChipProps) {
  return (
    <div className="composer-file-chip" title={tooltip ?? name}>
      <span className="composer-file-icon" aria-hidden>
        📄
      </span>
      <span className="composer-file-name">{name}</span>
      {size !== undefined && (
        <span className="composer-file-size">{formatSize(size)}</span>
      )}
      {onRemove && (
        <button
          type="button"
          className="composer-chip-close"
          onClick={onRemove}
          aria-label="移除"
        >
          ×
        </button>
      )}
    </div>
  );
}

type PendingFileChipProps = {
  pending: PendingFile;
  onRemove: () => void;
  onOpenVideo: (target: VideoPreviewTarget) => void;
};

function PendingFileChip({ pending, onRemove, onOpenVideo }: PendingFileChipProps) {
  const image = isImageFile(pending.file, pending.name);
  const video = !image && isVideoFile(pending.file, pending.name);
  const [thumbUrl, setThumbUrl] = useState<string | null>(null);
  const { openPreview, lightbox } = useImageLightbox();

  useEffect(() => {
    if (!image && !video) {
      setThumbUrl(null);
      return;
    }
    const url = URL.createObjectURL(pending.file);
    setThumbUrl(url);
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [image, video, pending.file]);

  if (image && thumbUrl) {
    return (
      <>
        <ImageThumbButton
          src={thumbUrl}
          alt={pending.name}
          onOpen={openPreview}
          onRemove={onRemove}
        />
        {lightbox}
      </>
    );
  }

  if (video && thumbUrl) {
    return (
      <div className="composer-video-chip" title={pending.name}>
        <VideoThumbButton
          src={thumbUrl}
          title={pending.name}
          className="composer-video-chip-preview-btn"
          videoClassName="composer-video-chip-preview"
          onOpen={onOpenVideo}
          onRemove={onRemove}
        />
        <span className="composer-file-name">{pending.name}</span>
        <span className="composer-file-size">{formatSize(pending.size)}</span>
      </div>
    );
  }

  return (
    <FileChip
      name={pending.name}
      size={pending.size}
      onRemove={onRemove}
    />
  );
}

export function ComposerTray({
  items,
  primaryPath,
  pendingFiles,
  mediaCapabilityHints = [],
  onSetPrimary,
  onRemoveDoc,
  onRemoveFile,
}: Props) {
  const { openPreview: openVideoPreview, lightbox: videoLightbox } =
    useVideoLightbox();

  if (
    items.length === 0 &&
    pendingFiles.length === 0 &&
    mediaCapabilityHints.length === 0
  ) {
    return null;
  }

  return (
    <div className="composer-tray">
      {mediaCapabilityHints.map((hint) => (
        <div key={hint} className="composer-tray-hint" role="status">
          {hint}
        </div>
      ))}
      {items.map((item) => {
        const canPrimary = isMarkdownPath(item.path);
        return (
          <DocChip
            key={item.path}
            title={item.title}
            tooltip={item.path}
            primary={canPrimary && item.path === primaryPath}
            onClick={canPrimary ? () => onSetPrimary(item.path) : undefined}
            onRemove={() => onRemoveDoc(item.path)}
          />
        );
      })}
      {pendingFiles.map((f) => (
        <PendingFileChip
          key={f.id}
          pending={f}
          onRemove={() => onRemoveFile(f.id)}
          onOpenVideo={openVideoPreview}
        />
      ))}
      {videoLightbox}
    </div>
  );
}
