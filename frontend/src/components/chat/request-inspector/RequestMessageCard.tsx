import { useEffect, useRef, useState } from "react";
import type { RequestMessage } from "../../../api";
import { categoryColor } from "../requestCategories";
import { compactTokenCount } from "../../../utils/chatMessageFormat";
import { FoldChevron } from "../../FoldChevron";
import { highlightMatches } from "./searchHighlight";
import { scrollToAndFlash, segmentDimmed } from "./requestInspectorGroups";
import type { ScrollTarget } from "./requestInspectorGroups";
import { segmentDisplayText, textMatches, toolCallsText } from "./requestSearchText";

const HISTORY_COLLAPSE_LINES = 6;
const SEGMENT_COLLAPSE_LINES = 40;
const SEGMENT_PREVIEW_LINES = 12;

type Props = {
  message: RequestMessage;
  label: string;
  categoryFilter: string | null;
  scrollTarget: ScrollTarget | null;
  searchQuery: string;
  activeMatch: number;
  matchOffset: number;
  onClearScroll: () => void;
};

function lineCount(text: string): number {
  return text ? text.split("\n").length : 0;
}

function firstLines(text: string, n: number): string {
  return text.split("\n").slice(0, n).join("\n");
}

export function RequestMessageCard({
  message,
  label,
  categoryFilter,
  scrollTarget,
  searchQuery,
  activeMatch,
  matchOffset,
  onClearScroll,
}: Props) {
  const ref = useRef<HTMLElement>(null);
  const isHistory = message.segments.some((s) => s.kind === "history");
  const [historyOpen, setHistoryOpen] = useState(!isHistory);
  const [segExpanded, setSegExpanded] = useState<Record<number, boolean>>({});

  useEffect(() => {
    if (!scrollTarget || scrollTarget.kind === "tools") return;
    if (scrollTarget.messageIndex !== message.index) return;
    scrollToAndFlash(
      scrollTarget.kind === "segment"
        ? ref.current?.querySelector(`[data-segment-index="${scrollTarget.segmentIndex}"]`)
        : ref.current,
    );
    onClearScroll();
  }, [scrollTarget, message.index, onClearScroll]);

  const texts = message.segments.map((seg) => segmentDisplayText(message, seg));
  const callsText = toolCallsText(message);
  // 命中的内容必须可见，否则高亮序号会指向收起的部分
  const hasHit =
    texts.some((t) => textMatches(t, searchQuery)) || textMatches(callsText, searchQuery);
  const historyShown = historyOpen || hasHit;

  let offset = matchOffset;
  const segmentNodes = message.segments.map((seg, i) => {
    const text = texts[i];
    const lines = lineCount(text);
    const long = lines > SEGMENT_COLLAPSE_LINES;
    const previewOnly =
      long && !segExpanded[i] && !textMatches(text, searchQuery) && historyShown;
    const shown = !historyShown
      ? firstLines(text, HISTORY_COLLAPSE_LINES)
      : previewOnly
        ? firstLines(text, SEGMENT_PREVIEW_LINES)
        : text;
    const { nodes, matchCount } = highlightMatches(shown, searchQuery, activeMatch, offset);
    offset += matchCount;
    const cat = seg.category || "unlabeled";
    return (
      <div
        key={i}
        data-segment-index={i}
        className={`reqinspector-seg${segmentDimmed(seg, categoryFilter) ? " reqinspector-seg--dim" : ""}`}
      >
        <div className="reqinspector-seg-bar" style={{ background: categoryColor(cat) }} />
        <div className="reqinspector-seg-inner">
          <span className="reqinspector-seg-tag">
            {cat === "unlabeled" ? "未标注" : seg.label}
          </span>
          {seg.media ? (
            <p className="reqinspector-seg-media">
              {seg.media.name}（{seg.media.type === "video" ? "视频" : "图片"}）
            </p>
          ) : (
            <pre className="reqinspector-seg-text">{nodes}</pre>
          )}
          {previewOnly ? (
            <button
              type="button"
              className="reqinspector-expand"
              onClick={() => setSegExpanded((s) => ({ ...s, [i]: true }))}
            >
              展开全部（{lines} 行）
            </button>
          ) : null}
        </div>
      </div>
    );
  });
  const callsNodes = callsText
    ? highlightMatches(callsText, searchQuery, activeMatch, offset).nodes
    : null;

  return (
    <article ref={ref} className="reqinspector-msg" data-message-index={message.index}>
      <header className="reqinspector-msg-head">
        <span className="reqinspector-msg-role">{message.role}</span>
        <span className="reqinspector-msg-label">{label}</span>
        <span className="reqinspector-msg-tokens">≈{compactTokenCount(message.tokens)}</span>
        {isHistory ? (
          <button
            type="button"
            className="reqinspector-fold-btn"
            onClick={() => setHistoryOpen((v) => !v)}
            aria-expanded={historyShown}
          >
            <FoldChevron open={historyShown} size={10} />
          </button>
        ) : null}
      </header>
      <div className="reqinspector-msg-body">
        {segmentNodes}
        {callsNodes ? (
          <div className="reqinspector-toolcalls">
            <pre className="reqinspector-seg-text">{callsNodes}</pre>
          </div>
        ) : null}
      </div>
    </article>
  );
}
