import { downloadUrl } from "../api";
import { isLikelyImagePath } from "../utils/kbImageUrls";

function basename(path: string): string {
  return path.split("/").pop() || path;
}

type Props = {
  paths: string[];
  className?: string;
  imageClassName?: string;
  linkClassName?: string;
};

/** 知识库相对路径附件的内联预览（图片）或下载链。 */
export function KbAttachmentList({
  paths,
  className = "kb-attachment-list",
  imageClassName = "kb-attachment-image",
  linkClassName = "kb-attachment-image-link",
}: Props) {
  if (!paths.length) return null;
  return (
    <div className={className}>
      {paths.map((path) =>
        isLikelyImagePath(path) ? (
          <a
            key={path}
            className={linkClassName}
            href={downloadUrl(path, { download: true })}
            title={path}
          >
            <img
              className={imageClassName}
              src={downloadUrl(path)}
              alt={basename(path)}
              loading="lazy"
            />
          </a>
        ) : (
          <div key={path}>
            <a href={downloadUrl(path, { download: true })}>
              下载附件：{basename(path)}
            </a>
          </div>
        ),
      )}
    </div>
  );
}
