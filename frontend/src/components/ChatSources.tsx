import { useState } from "react";
import { dedupeSources, downloadUrl, type SourceRef } from "../api";
import { isLikelyImagePath } from "../utils/kbImageUrls";
import { ImageThumbButton } from "./ImageThumbButton";
import { SourceChip } from "./SourceChip";
import { useImageLightbox } from "../hooks/useImageLightbox";

type Props = {
  sources: SourceRef[];
  previewPath?: string | null;
  onOpen: (src: SourceRef) => void;
  /** 已在时间线附件中展示的图片路径，参考区不再出瓦片 */
  hideImagePaths?: string[];
};

function basename(path: string): string {
  return path.split("/").pop() || path;
}

function isKbImageSource(
  src: SourceRef,
): src is Extract<SourceRef, { type: "kb" }> {
  return src.type === "kb" && isLikelyImagePath(src.path);
}

export function ChatSources({
  sources,
  previewPath,
  onOpen,
  hideImagePaths,
}: Props) {
  const hidden = new Set(hideImagePaths ?? []);
  const items = dedupeSources(sources).filter(
    (s) => !(isKbImageSource(s) && hidden.has(s.path)),
  );
  const imageSources = items.filter(isKbImageSource);
  const otherSources = items.filter((s) => !isKbImageSource(s));
  const hasConversation = items.some((s) => s.type === "conversation");
  // 会话引用 / 图片瓦片需要可点查看：有会话或图片时默认展开
  const [open, setOpen] = useState(hasConversation || imageSources.length > 0);
  const { openPreview, lightbox } = useImageLightbox();

  if (items.length === 0) return null;

  const hasKb = items.some((s) => s.type === "kb");
  const sectionTitle =
    hasConversation && !hasKb ? "参考会话" : hasConversation ? "参考来源" : "参考文档";
  return (
    <div className="chat-sources">
      <button
        type="button"
        className="chat-sources-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="chat-sources-title">{sectionTitle}</span>
        <span className="chat-sources-count">{items.length} 项</span>
        <span className="chat-sources-chevron" aria-hidden>
          {open ? "▾" : "▸"}
        </span>
      </button>
      {open && (
        <div className="chat-sources-body">
          {imageSources.length > 0 && (
            <div className="chat-sources-tiles">
              {imageSources.map((src) => (
                <ImageThumbButton
                  key={src.path}
                  src={downloadUrl(src.path)}
                  alt={basename(src.path)}
                  title={`${src.path}（点击查看大图）`}
                  className="chat-sources-tile"
                  imageClassName="chat-sources-tile-img"
                  downloadHref={downloadUrl(src.path, { download: true })}
                  onOpen={openPreview}
                />
              ))}
            </div>
          )}
          {otherSources.length > 0 && (
            <div className="chat-sources-links">
              {otherSources.map((src, j) => (
                <SourceChip
                  key={`${src.type}-${j}`}
                  source={src}
                  active={src.type === "kb" && previewPath === src.path}
                  onOpen={onOpen}
                />
              ))}
            </div>
          )}
        </div>
      )}
      {lightbox}
    </div>
  );
}
