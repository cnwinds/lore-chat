import {
  isDisplayableImageRef,
  isMediaGrantUrl,
  mediaDisplayUrl,
} from "../utils/kbImageUrls";
import { isLikelyVideoPath } from "../utils/kbVideoUrls";
import { ImageThumbButton } from "./ImageThumbButton";
import { VideoThumbButton } from "./VideoThumbButton";
import { useImageLightbox } from "../hooks/useImageLightbox";
import { useVideoLightbox } from "../hooks/useVideoLightbox";

function isDisplayableVideo(path: string): boolean {
  const s = path.trim();
  if (/^https?:\/\//i.test(s)) return isMediaGrantUrl(s);
  return isLikelyVideoPath(s);
}

function basename(path: string): string {
  const raw = path.split("/").pop() || path;
  try {
    return decodeURIComponent(raw.split("?")[0] || raw);
  } catch {
    return raw;
  }
}

type Props = {
  paths: string[];
  className?: string;
  imageClassName?: string;
  /** 缩略图外层样式（timeline / chat 可覆盖） */
  thumbClassName?: string;
};

/** 知识库相对路径附件：图片缩略预览（点开大图），视频点击播放，其它为下载链。 */
export function KbAttachmentList({
  paths,
  className = "kb-attachment-list",
  imageClassName = "kb-attachment-image",
  thumbClassName = "kb-attachment-image-link",
}: Props) {
  const { openPreview, lightbox } = useImageLightbox();
  const { openPreview: openVideoPreview, lightbox: videoLightbox } =
    useVideoLightbox();

  if (!paths.length) return null;

  return (
    <div className={className}>
      {paths.map((path) =>
        isDisplayableImageRef(path) ? (
          <ImageThumbButton
            key={path}
            src={mediaDisplayUrl(path)}
            alt={basename(path)}
            title={`${basename(path)}（点击查看大图）`}
            className={`${thumbClassName} kb-attachment-image-btn`}
            imageClassName={imageClassName}
            downloadHref={mediaDisplayUrl(path)}
            onOpen={openPreview}
          />
        ) : isDisplayableVideo(path) ? (
          <div key={path} className="kb-attachment-video-wrap">
            <VideoThumbButton
              src={mediaDisplayUrl(path)}
              title={basename(path)}
              className="kb-attachment-video-btn"
              videoClassName="kb-attachment-video"
              downloadHref={mediaDisplayUrl(path)}
              onOpen={openVideoPreview}
            />
            <a
              className="kb-attachment-video-download"
              href={mediaDisplayUrl(path)}
            >
              下载：{basename(path)}
            </a>
          </div>
        ) : (
          <div key={path}>
            <a href={mediaDisplayUrl(path)}>
              下载附件：{basename(path)}
            </a>
          </div>
        ),
      )}
      {lightbox}
      {videoLightbox}
    </div>
  );
}
