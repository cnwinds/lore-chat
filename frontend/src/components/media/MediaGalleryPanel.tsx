import { useEffect, useMemo, useState } from "react";
import { downloadUrl, getTree } from "../../api";
import { useImageLightbox } from "../../hooks/useImageLightbox";
import { listDirectChildren } from "../../utils/kbMediaPaths";
import { isLikelyImagePath } from "../../utils/kbImageUrls";
import { pathBasename } from "../../utils/kbPath";
import type { DocWidth } from "../../types/doc";
import { ImageThumbButton } from "../ImageThumbButton";

type Props = {
  directory: string;
  refreshKey?: number;
  /** 侧栏已拉取的全库路径；有则不再单独 getTree */
  paths?: string[] | null;
  docWidth?: DocWidth;
  onClose: () => void;
  onToggleWidth?: () => void;
};

function pathSegments(dir: string): string[] {
  return dir.split("/").filter(Boolean);
}

/**
 * 媒体末级目录图库内容：由浮窗层承载，瓦片浏览，点击看大图。
 */
export function MediaGalleryPanel({
  directory,
  refreshKey = 0,
  paths: pathsProp = null,
  docWidth = "wide",
  onClose,
  onToggleWidth,
}: Props) {
  const [fetchedPaths, setFetchedPaths] = useState<string[]>([]);
  const [loading, setLoading] = useState(pathsProp == null);
  const [error, setError] = useState<string | null>(null);
  const { openPreview, lightbox } = useImageLightbox();

  const useSharedPaths = pathsProp != null;

  useEffect(() => {
    if (useSharedPaths) {
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    getTree()
      .then((r) => {
        if (!cancelled) setFetchedPaths(r.docs ?? []);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "加载失败");
          setFetchedPaths([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [directory, refreshKey, useSharedPaths]);

  const paths = useSharedPaths ? pathsProp : fetchedPaths;

  const children = useMemo(
    () => listDirectChildren(directory, paths),
    [directory, paths],
  );
  const images = useMemo(
    () => children.filter((p) => isLikelyImagePath(p)),
    [children],
  );
  const others = useMemo(
    () => children.filter((p) => !isLikelyImagePath(p)),
    [children],
  );

  const segments = pathSegments(directory);
  const title = segments[segments.length - 1] || directory;

  return (
    <div
      className={`kb-float-panel kb-float-panel--${docWidth}`}
      aria-label={`媒体图库：${directory}`}
    >
      <header className="kb-float-header">
        <div className="kb-float-header-main">
          <div className="kb-float-kicker">媒体图库</div>
          <h2 className="kb-float-title" title={directory}>
            {title}
          </h2>
          <nav className="kb-float-crumb" aria-label="路径">
            {segments.map((seg, i) => (
              <span key={`${i}-${seg}`} className="kb-float-crumb-seg">
                {i > 0 ? (
                  <span className="kb-float-crumb-sep" aria-hidden>
                    /
                  </span>
                ) : null}
                <span className={i === segments.length - 1 ? "is-current" : ""}>
                  {seg}
                </span>
              </span>
            ))}
          </nav>
        </div>
        <div className="kb-float-header-actions">
          {onToggleWidth ? (
            <button
              type="button"
              className="doc-icon-btn"
              title={docWidth === "wide" ? "变窄" : "变宽"}
              onClick={onToggleWidth}
            >
              {docWidth === "wide" ? "⟧" : "⟦"}
            </button>
          ) : null}
          <button
            type="button"
            className="doc-icon-btn"
            title="关闭"
            aria-label="关闭"
            onClick={onClose}
          >
            ×
          </button>
        </div>
      </header>

      <div className="kb-float-meta">
        {loading
          ? "加载中…"
          : error
            ? null
            : `${images.length} 张图片${
                others.length > 0 ? ` · ${others.length} 个其他文件` : ""
              }`}
      </div>

      <div className="kb-float-body">
        {error && <div className="kb-float-error">错误：{error}</div>}
        {!loading && !error && images.length === 0 && others.length === 0 && (
          <div className="kb-float-empty">
            <div className="kb-float-empty-mark" aria-hidden />
            <p>此目录暂无文件</p>
            <p className="kb-float-empty-hint">
              生成或上传的图片会出现在这里
            </p>
          </div>
        )}
        {images.length > 0 && (
          <div className="media-gallery-grid">
            {images.map((path) => {
              const name = pathBasename(path);
              return (
                <figure key={path} className="media-gallery-tile">
                  <ImageThumbButton
                    src={downloadUrl(path)}
                    alt={name}
                    title={`${path}（点击查看大图）`}
                    className="media-gallery-tile-btn"
                    imageClassName="media-gallery-tile-img"
                    downloadHref={downloadUrl(path, { download: true })}
                    onOpen={openPreview}
                  />
                  <figcaption className="media-gallery-tile-caption" title={name}>
                    {name}
                  </figcaption>
                </figure>
              );
            })}
          </div>
        )}
        {others.length > 0 && (
          <section className="media-gallery-others">
            <h3 className="media-gallery-others-title">其他文件</h3>
            <ul className="media-gallery-others-list">
              {others.map((path) => (
                <li key={path}>
                  <a
                    href={downloadUrl(path, { download: true })}
                    className="media-gallery-other-link"
                    title={path}
                  >
                    {pathBasename(path)}
                  </a>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
      {lightbox}
    </div>
  );
}
