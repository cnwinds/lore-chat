import type { SourceRef } from "../api";
import { formatMonthDay } from "../utils/displayTime";

type Props = {
  source: SourceRef;
  active?: boolean;
  onOpen: (src: SourceRef) => void;
};

function formatConvTs(ts?: string): string | null {
  if (!ts) return null;
  const out = formatMonthDay(ts);
  return out || ts.slice(0, 10) || null;
}

function conversationExcerptPreview(excerpt?: string): string {
  if (!excerpt) return "";
  return excerpt.replace(/\s+/g, " ").trim().slice(0, 28);
}

function linkLabel(src: SourceRef): string {
  if (src.type === "kb") {
    return src.path.split("/").pop() || src.path;
  }
  if (src.type === "conversation") {
    const when = formatConvTs(src.ts);
    const title = src.conversation_title?.trim();
    const excerpt = conversationExcerptPreview(src.excerpt);
    if (title && excerpt) {
      return `${when ? `${when} · ` : ""}${title}：${excerpt}`;
    }
    if (title) return when ? `${when} · ${title}` : title;
    if (excerpt) return when ? `${when} · ${excerpt}` : excerpt;
    return `会话 ${src.cid.slice(0, 6)}`;
  }
  return src.title || src.url;
}

function linkTitle(src: SourceRef): string {
  if (src.type === "kb") return src.path;
  if (src.type === "conversation") {
    const parts = [
      src.conversation_title?.trim(),
      formatConvTs(src.ts) ?? undefined,
      src.role === "user" ? "用户" : src.role === "assistant" ? "助手" : src.role,
      src.excerpt?.trim(),
    ].filter(Boolean);
    return parts.join(" · ") || "历史会话（点击跳转到原文）";
  }
  return src.url;
}

function sourceIcon(src: SourceRef): string {
  if (src.type === "kb") return "📄";
  if (src.type === "web") return "🔗";
  if (src.type === "conversation") return "💬";
  return "🔍";
}

export function SourceChip({ source, active, onOpen }: Props) {
  return (
    <button
      type="button"
      className={`source-link${active ? " active" : ""}`}
      title={linkTitle(source)}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onOpen(source);
      }}
    >
      <span className="source-link-icon" aria-hidden>
        {sourceIcon(source)}
      </span>
      <span className="source-link-text">{linkLabel(source)}</span>
    </button>
  );
}
