import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { MessageRangeHighlight } from "./MessageRangeHighlight";

export const USER_MESSAGE_PREVIEW_LINES = 6;

export function userMessageCollapsedMaxHeight(
  lineHeightPx: number,
  lines = USER_MESSAGE_PREVIEW_LINES,
): number {
  return lineHeightPx * lines;
}

export function userMessageTextOverflows(
  scrollHeightPx: number,
  lineHeightPx: number,
  lines = USER_MESSAGE_PREVIEW_LINES,
): boolean {
  if (!Number.isFinite(scrollHeightPx) || !Number.isFinite(lineHeightPx) || lineHeightPx <= 0) {
    return false;
  }
  return scrollHeightPx > userMessageCollapsedMaxHeight(lineHeightPx, lines) + 1;
}

type CollapsibleUserTextProps = {
  text: string;
  highlightRange?: { start: number; end: number } | null;
};

export function CollapsibleUserText({
  text,
  highlightRange = null,
}: CollapsibleUserTextProps) {
  const contentRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [overflows, setOverflows] = useState(false);
  const [collapsedMaxPx, setCollapsedMaxPx] = useState<number | null>(null);

  const remeasure = useCallback(() => {
    const el = contentRef.current;
    if (!el) return;
    const lineHeight = parseFloat(window.getComputedStyle(el).lineHeight);
    if (!Number.isFinite(lineHeight) || lineHeight <= 0) return;
    setCollapsedMaxPx(userMessageCollapsedMaxHeight(lineHeight));
    setOverflows(userMessageTextOverflows(el.scrollHeight, lineHeight));
  }, []);

  useEffect(() => {
    setExpanded(false);
  }, [text]);

  useEffect(() => {
    if (highlightRange) setExpanded(true);
  }, [highlightRange]);

  useLayoutEffect(() => {
    remeasure();
  }, [text, remeasure]);

  useLayoutEffect(() => {
    const el = contentRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => remeasure());
    ro.observe(el);
    return () => ro.disconnect();
  }, [text, remeasure]);

  const showToggle = overflows;
  const collapsed = showToggle && !expanded;

  const body = highlightRange ? (
    <MessageRangeHighlight
      text={text}
      start={highlightRange.start}
      end={highlightRange.end}
    />
  ) : (
    text
  );

  return (
    <div
      className={`chat-user-text-wrap${collapsed ? " chat-user-text-wrap--collapsed" : ""}`}
    >
      <div
        ref={contentRef}
        className="chat-user-text"
        style={
          collapsed && collapsedMaxPx != null
            ? { maxHeight: collapsedMaxPx }
            : undefined
        }
      >
        {body}
      </div>
      {showToggle ? (
        <div className="chat-user-text-footer">
          <button
            type="button"
            className="chat-user-text-toggle"
            aria-expanded={expanded}
            onClick={() => setExpanded((v) => !v)}
          >
            <span className="chat-user-text-toggle-label">
              {expanded ? "收起" : "展开全文"}
            </span>
            <span
              className={`chat-user-text-toggle-chevron${expanded ? " chat-user-text-toggle-chevron--up" : ""}`}
              aria-hidden
            />
          </button>
        </div>
      ) : null}
    </div>
  );
}
