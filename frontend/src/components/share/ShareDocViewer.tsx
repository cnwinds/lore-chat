import { useEffect, useMemo, useRef } from "react";
import { MarkdownContent } from "../MarkdownContent";
import { useShareDocOutlineActive } from "../../hooks/useShareDocOutlineActive";
import {
  jumpToShareDocOutline,
  mapOutlineHeadingIds,
  parseDocOutline,
  type OutlineItem,
} from "../../utils/docOutline";

type Props = {
  body: string;
};

export function ShareDocViewer({ body }: Props) {
  const bodyScrollRef = useRef<HTMLElement | null>(null);
  const activeItemRef = useRef<HTMLButtonElement | null>(null);

  const outlineItems = useMemo(
    () => mapOutlineHeadingIds(parseDocOutline(body)),
    [body],
  );

  const activeIndex = useShareDocOutlineActive({
    items: outlineItems,
    scrollRootRef: bodyScrollRef,
    enabled: outlineItems.length > 0,
  });

  useEffect(() => {
    if (activeIndex < 0) return;
    activeItemRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [activeIndex]);

  const handleJump = (item: OutlineItem) => {
    jumpToShareDocOutline(bodyScrollRef.current, item);
  };

  const hasOutline = outlineItems.length > 0;

  return (
    <div
      className={`share-page-doc-layout${hasOutline ? "" : " share-page-doc-layout--solo"}`}
    >
      {hasOutline && (
        <aside className="share-page-doc-outline" aria-label="文档目录">
          <div className="share-page-doc-outline-head">
            <span className="share-page-doc-outline-title">目录</span>
            <span className="share-page-doc-outline-count" aria-hidden>
              {outlineItems.length}
            </span>
          </div>
          <nav className="share-page-doc-outline-list" aria-label="章节导航">
            {outlineItems.map((item, i) => {
              const isActive = i === activeIndex;
              return (
                <button
                  key={item.id}
                  ref={isActive ? activeItemRef : undefined}
                  type="button"
                  className={`share-page-doc-outline-item${isActive ? " is-active" : ""}`}
                  style={{ paddingLeft: `${12 + (item.level - 1) * 12}px` }}
                  title={item.text}
                  aria-current={isActive ? "location" : undefined}
                  onClick={() => handleJump(item)}
                >
                  <span className="share-page-doc-outline-level" aria-hidden>
                    H{item.level}
                  </span>
                  <span className="share-page-doc-outline-text">{item.text}</span>
                </button>
              );
            })}
          </nav>
        </aside>
      )}
      <article
        ref={bodyScrollRef}
        className="share-page-doc-body markdown-body"
        aria-label="文档正文"
      >
        <div className="share-page-doc-body-inner">
          <MarkdownContent outlineHeadingIds>{body}</MarkdownContent>
        </div>
      </article>
    </div>
  );
}
