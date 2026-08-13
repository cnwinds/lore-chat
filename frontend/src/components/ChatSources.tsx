import { useState } from "react";
import { dedupeSources, type SourceRef } from "../api";
import { SourceChip } from "./SourceChip";

type Props = {
  sources: SourceRef[];
  previewPath?: string | null;
  onOpen: (src: SourceRef) => void;
};

export function ChatSources({ sources, previewPath, onOpen }: Props) {
  const items = dedupeSources(sources);
  if (items.length === 0) return null;

  const hasConversation = items.some((s) => s.type === "conversation");
  const hasKb = items.some((s) => s.type === "kb");
  const sectionTitle =
    hasConversation && !hasKb ? "参考会话" : hasConversation ? "参考来源" : "参考文档";
  // 会话引用需要可点跳转：有会话来源时默认展开
  const [open, setOpen] = useState(hasConversation);
  return (
    <div className="chat-sources">
      <button
        type="button"
        className="chat-sources-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="chat-sources-title">{sectionTitle}</span>
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
