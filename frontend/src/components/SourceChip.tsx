import type { SourceRef } from "../api";

type Props = {
  source: SourceRef;
  active?: boolean;
  onOpen: (src: SourceRef) => void;
};

function linkLabel(src: SourceRef): string {
  if (src.type === "kb") {
    return src.path.split("/").pop() || src.path;
  }
  if (src.type === "conversation") {
    return `会话记录 ${src.cid.slice(0, 6)}`;
  }
  return src.title || src.url;
}

function linkTitle(src: SourceRef): string {
  if (src.type === "kb") return src.path;
  if (src.type === "conversation") return "未归档会话（可检索的临时记录）";
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
