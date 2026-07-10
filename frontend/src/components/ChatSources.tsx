import { useState } from "react";
import { dedupeSources, type SourceRef } from "../api";
import { SourceChip } from "./SourceChip";

type Props = {
  sources: SourceRef[];
  previewPath?: string | null;
  onOpen: (src: SourceRef) => void;
};

export function ChatSources({ sources, previewPath, onOpen }: Props) {
  const [open, setOpen] = useState(false);
  const items = dedupeSources(sources);
  if (items.length === 0) return null;

  return (
    <div className="chat-sources">
      <button
        type="button"
        className="chat-sources-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="chat-sources-title">参考文档</span>
        <span className="chat-sources-count">{items.length} 项</span>
        <span className="chat-sources-chevron" aria-hidden>
          {open ? "▾" : "▸"}
        </span>
      </button>
      {open && (
        <div className="chat-sources-links">
          {items.map((src, j) => (
            <SourceChip
              key={`${src.type}-${j}`}
              source={src}
              active={src.type === "kb" && previewPath === src.path}
              onOpen={onOpen}
            />
          ))}
        </div>
      )}
    </div>
  );
}
