import { downloadUrl } from "../api";
import { isLikelyImagePath } from "../utils/kbImageUrls";
import { isLikelyVideoPath } from "../utils/kbVideoUrls";
import { ImageThumbButton } from "./ImageThumbButton";
import { useImageLightbox } from "../hooks/useImageLightbox";

function basename(path: string): string {
  return path.split("/").pop() || path;
}

type Props = {
  paths: string[];
  className?: string;
  imageClassName?: string;
  /** 缩略图外层样式（timeline / chat 可覆盖） */
  thumbClassName?: string;
};

/** 知识库相对路径附件：图片缩略预览（点开大图，可下载），其它为下载链。 */
export function KbAttachmentList({
  paths,
  className = "kb-attachment-list",
  imageClassName = "kb-attachment-image",
  thumbClassName = "kb-attachment-image-link",
}: Props) {
  const { openPreview, lightbox } = useImageLightbox();

  if (!paths.length) return null;

  return (
    <div className={className}>
      {paths.map((path) =>
        isLikelyImagePath(path) ? (
          <ImageThumbButton
            key={path}
            src={downloadUrl(path)}
            alt={basename(path)}
            title={`${path}（点击查看大图）`}
            className={`${thumbClassName} kb-attachment-image-btn`}
            imageClassName={imageClassName}
            downloadHref={downloadUrl(path, { download: true })}
            onOpen={openPreview}
          />
        ) : isLikelyVideoPath(path) ? (
          <div key={path} className="kb-attachment-video-wrap">
            <video
              className="kb-attachment-video"
              src={downloadUrl(path)}
              controls
              preload="metadata"
              title={path}
            />
            <a
              className="kb-attachment-video-download"
              href={downloadUrl(path, { download: true })}
            >
              下载：{basename(path)}
            </a>
          </div>
        ) : (
          <div key={path}>
            <a href={downloadUrl(path, { download: true })}>
              下载附件：{basename(path)}
            </a>
          </div>
        ),
      )}
      {lightbox}
    </div>
  );
}
