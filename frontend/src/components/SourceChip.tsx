import type { SourceRef } from "../api";

type Props = {
  source: SourceRef;
  onOpenSource: (src: SourceRef) => void;
};

function chipLabel(src: SourceRef): string {
  if (src.type === "kb") {
    return src.path.split("/").pop() || src.path;
  }
  return src.title || src.url;
}

export function SourceChip({ source, onOpenSource }: Props) {
  return (
    <button
      type="button"
      className="source-chip"
      onClick={() => onOpenSource(source)}
      title={
        source.type === "kb"
          ? source.path
          : source.type === "web"
            ? source.url
            : source.url
      }
    >
      {source.type === "kb" ? "📄 " : source.type === "web" ? "🔗 " : "🔍 "}
      {chipLabel(source)}
    </button>
  );
}
