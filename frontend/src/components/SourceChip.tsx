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
  return src.title || src.url;
}

function linkTitle(src: SourceRef): string {
  if (src.type === "kb") return src.path;
  return src.url;
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
        {source.type === "kb" ? "📄" : source.type === "web" ? "🔗" : "🔍"}
      </span>
      <span className="source-link-text">{linkLabel(source)}</span>
    </button>
  );
}
