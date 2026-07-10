import { useState } from "react";
import type { SourceRef, TimelineBlock } from "../api";
import { MarkdownContent } from "./MarkdownContent";
import { SourceChip } from "./SourceChip";

type Props = {
  block: TimelineBlock;
  onOpenSource: (src: SourceRef) => void;
};

function formatTs(ts: string): string {
  try {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return "";
  }
}

function ToolBlockView({
  block,
  onOpenSource,
}: {
  block: Extract<TimelineBlock, { type: "tool" }>;
  onOpenSource: (src: SourceRef) => void;
}) {
  const [open, setOpen] = useState(block.status === "running");
  const time = formatTs(block.ts);

  return (
    <div className={`timeline-tool timeline-tool-${block.status}`}>
      <button
        type="button"
        className="timeline-tool-header"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="timeline-tool-label">
          {block.status === "running" ? "⏳" : "✓"} {block.label}
        </span>
        {time && <span className="timeline-ts">{time}</span>}
        {block.duration_ms !== undefined && (
          <span className="timeline-duration">{block.duration_ms}ms</span>
        )}
        <span className="timeline-tool-chevron">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="timeline-tool-body">
          {block.summary && <div className="timeline-tool-summary">{block.summary}</div>}
          {block.sources && block.sources.length > 0 && (
            <div className="timeline-tool-sources">
              {block.sources.map((src, i) => (
                <SourceChip
                  key={`${src.type}-${i}`}
                  source={src}
                  onOpenSource={onOpenSource}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function TimelineBlockView({ block, onOpenSource }: Props) {
  if (block.type === "tool") {
    return <ToolBlockView block={block} onOpenSource={onOpenSource} />;
  }

  if (block.type === "parallel") {
    const time = formatTs(block.ts);
    return (
      <div className="timeline-parallel">
        <div className="timeline-parallel-header">
          <span>检索资料</span>
          {time && <span className="timeline-ts">{time}</span>}
          {block.duration_ms !== undefined && (
            <span className="timeline-duration">{block.duration_ms}ms</span>
          )}
        </div>
        <div className="timeline-parallel-children">
          {block.children.map((child, i) => (
            <TimelineBlockView
              key={
                child.type === "tool"
                  ? child.id
                  : child.type === "parallel"
                    ? child.batch_id
                    : `text-${i}`
              }
              block={child}
              onOpenSource={onOpenSource}
            />
          ))}
        </div>
      </div>
    );
  }

  const time = formatTs(block.ts);
  return (
    <div className="timeline-text">
      {time && <span className="timeline-ts timeline-text-ts">{time}</span>}
      <MarkdownContent className="markdown-body chat-markdown">
        {block.content}
      </MarkdownContent>
    </div>
  );
}
