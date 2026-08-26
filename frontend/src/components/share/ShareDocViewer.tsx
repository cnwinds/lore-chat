import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { MarkdownContent } from "../MarkdownContent";
import { OutlineIcon } from "../DocToolbarIcons";
import { useNarrowViewport } from "../../hooks/useNarrowViewport";
import { useScrollLock } from "../../hooks/useScrollLock";
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

type OutlineListProps = {
  items: OutlineItem[];
  activeIndex: number;
  activeItemRef: RefObject<HTMLButtonElement | null>;
  onJump: (item: OutlineItem) => void;
  className: string;
};

function ShareDocOutlineList({
  items,
  activeIndex,
  activeItemRef,
  onJump,
  className,
}: OutlineListProps) {
  return (
    <nav className={className} aria-label="章节导航">
      {items.map((item, i) => {
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
            onClick={() => onJump(item)}
          >
            <span className="share-page-doc-outline-level" aria-hidden>
              H{item.level}
            </span>
            <span className="share-page-doc-outline-text">{item.text}</span>
          </button>
        );
      })}
    </nav>
  );
}

export function ShareDocViewer({ body }: Props) {
  const bodyScrollRef = useRef<HTMLElement | null>(null);
  const activeItemRef = useRef<HTMLButtonElement | null>(null);
  const closeBtnRef = useRef<HTMLButtonElement | null>(null);
  const narrow = useNarrowViewport();
  const [mobileOutlineOpen, setMobileOutlineOpen] = useState(false);

  const outlineItems = useMemo(
    () => mapOutlineHeadingIds(parseDocOutline(body)),
    [body],
  );

  const activeIndex = useShareDocOutlineActive({
    items: outlineItems,
    scrollRootRef: bodyScrollRef,
    enabled: outlineItems.length > 0,
  });

  const hasOutline = outlineItems.length > 0;
  const sheetOpen = narrow && mobileOutlineOpen;

  useEffect(() => {
    if (!narrow) setMobileOutlineOpen(false);
  }, [narrow]);

  useEffect(() => {
    if (activeIndex < 0) return;
    if (!narrow || mobileOutlineOpen) {
      activeItemRef.current?.scrollIntoView?.({ block: "nearest" });
    }
  }, [activeIndex, narrow, mobileOutlineOpen]);

  useEffect(() => {
    if (!sheetOpen) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        setMobileOutlineOpen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [sheetOpen]);

  useScrollLock(sheetOpen, bodyScrollRef);

  useEffect(() => {
    if (!sheetOpen) return;
    closeBtnRef.current?.focus?.();
  }, [sheetOpen]);

  const handleJump = (item: OutlineItem) => {
    jumpToShareDocOutline(bodyScrollRef.current, item);
    if (narrow) setMobileOutlineOpen(false);
  };

  const layoutClass = [
    "share-page-doc-layout",
    hasOutline ? "" : "share-page-doc-layout--solo",
    narrow && hasOutline ? "share-page-doc-layout--mobile" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={layoutClass}>
      {hasOutline && !narrow && (
        <aside className="share-page-doc-outline" aria-label="文档目录">
          <div className="share-page-doc-outline-head">
            <span className="share-page-doc-outline-title">目录</span>
            <span className="share-page-doc-outline-count" aria-hidden>
              {outlineItems.length}
            </span>
          </div>
          <ShareDocOutlineList
            items={outlineItems}
            activeIndex={activeIndex}
            activeItemRef={activeItemRef}
            onJump={handleJump}
            className="share-page-doc-outline-list"
          />
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
      {hasOutline && narrow && (
        <>
          <button
            type="button"
            className="share-sheet-fab"
            aria-label={`打开目录（${outlineItems.length} 个章节）`}
            aria-expanded={mobileOutlineOpen}
            aria-controls="share-doc-toc-sheet"
            onClick={() => setMobileOutlineOpen(true)}
          >
            <OutlineIcon size={18} />
            <span className="share-sheet-fab-label">目录</span>
            <span className="share-sheet-fab-badge" aria-hidden>
              {outlineItems.length}
            </span>
          </button>
          {mobileOutlineOpen && (
            <>
              <button
                type="button"
                className="share-sheet-backdrop"
                aria-label="关闭目录"
                onClick={() => setMobileOutlineOpen(false)}
              />
              <div
                id="share-doc-toc-sheet"
                className="share-sheet-panel"
                role="dialog"
                aria-modal="true"
                aria-label="文档目录"
              >
                <div className="share-sheet-handle" aria-hidden />
                <div className="share-page-doc-outline-head share-sheet-head">
                  <span className="share-page-doc-outline-title">目录</span>
                  <button
                    ref={closeBtnRef}
                    type="button"
                    className="share-sheet-close"
                    aria-label="关闭目录"
                    onClick={() => setMobileOutlineOpen(false)}
                  >
                    ×
                  </button>
                </div>
                <ShareDocOutlineList
                  items={outlineItems}
                  activeIndex={activeIndex}
                  activeItemRef={activeItemRef}
                  onJump={handleJump}
                  className="share-page-doc-outline-list share-sheet-list"
                />
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
