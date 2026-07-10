import { useState } from "react";
import {
  formatDuration,
  type CumulativeInfo,
  type IngestResult,
  type QuestionOption,
  type SourceRef,
  type TimelineBlock,
} from "../api";
import { MarkdownContent } from "./MarkdownContent";
import { PendingQuestion } from "./PendingQuestion";
import { SourceChip } from "./SourceChip";

type Props = {
  block: TimelineBlock;
  cumulative: CumulativeInfo;
  liveElapsedMs?: number;
  inParallel?: boolean;
  durationBold?: boolean;
  previewPath?: string | null;
  onOpenSource: (src: SourceRef) => void;
  conversationId?: string | null;
  onQuestionResolved?: (
    blockId: string,
    result: IngestResult,
    choiceLabel: string,
  ) => void;
};

/** 折叠时单行摘要：工具类型 + 关键结果 */
function toolOneLiner(block: Extract<TimelineBlock, { type: "tool" }>): string | undefined {
  if (block.status === "running") {
    return block.query || "执行中…";
  }
  if (block.tool === "fetch_url") {
    const web = block.sources?.find((s) => s.type === "web");
    if (web) return web.url;
  }
  if (
    (block.tool === "web_search" || block.tool === "search_kb") &&
    block.query
  ) {
    return block.summary ? `${block.query} · ${block.summary}` : block.query;
  }
  return block.summary;
}

/** 并行组内各工具步耗时的最大值 */
function maxParallelDuration(children: TimelineBlock[]): number | undefined {
  let max: number | undefined;
  for (const child of children) {
    if (child.type === "tool" && child.duration_ms !== undefined) {
      max = max === undefined ? child.duration_ms : Math.max(max, child.duration_ms);
    }
  }
  return max;
}

function ToolBlockView({
  block,
  liveElapsedMs,
  durationBold,
  onOpenSource,
  previewPath,
  conversationId,
  onQuestionResolved,
}: {
  block: Extract<TimelineBlock, { type: "tool" }>;
  liveElapsedMs?: number;
  durationBold?: boolean;
  onOpenSource: (src: SourceRef) => void;
  previewPath?: string | null;
  conversationId?: string | null;
  onQuestionResolved?: (
    blockId: string,
    result: IngestResult,
    choiceLabel: string,
  ) => void;
}) {
  const needsChoice =
    block.tool === "ask_user" &&
    block.status === "done" &&
    !!block.question_id &&
    !!block.options?.length;
  const [open, setOpen] = useState(block.status === "running" || needsChoice);
  const oneLiner = toolOneLiner(block);
  const displayMs =
    block.status === "running" && liveElapsedMs !== undefined
      ? liveElapsedMs
      : block.duration_ms;

  return (
    <div className={`timeline-tool timeline-tool-${block.status}`}>
      <button
        type="button"
        className={`timeline-tool-header${open ? "" : " timeline-tool-header-collapsed"}`}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        title={!open && oneLiner ? `${block.label}  ${oneLiner}` : undefined}
      >
        <span className="timeline-tool-label">
          <span className="timeline-tool-name">
            {block.status === "running" ? "⏳" : "✓"} {block.label}
          </span>
          {!open && oneLiner && (
            <span className="timeline-tool-oneline">{oneLiner}</span>
          )}
        </span>
        {displayMs !== undefined && (
          <span
            className={`timeline-duration${durationBold ? " timeline-duration-bold" : ""}`}
          >
            {formatDuration(displayMs)}
          </span>
        )}
        <span className="timeline-tool-chevron">{open ? "▾" : "▸"}</span>
      </button>
      {open &&
        (block.tool === "web_search" || block.tool === "search_kb") &&
        block.query && (
          <div className="timeline-tool-query">{block.query}</div>
        )}
      {open && block.status === "done" && block.sources && block.sources.length > 0 && (
        <div className="timeline-tool-sources timeline-tool-sources-inline">
          {block.sources.map((src, i) => (
            <SourceChip
              key={`${src.type}-${i}`}
              source={src}
              active={src.type === "kb" && previewPath === src.path}
              onOpen={onOpenSource}
            />
          ))}
        </div>
      )}
      {open && block.content && block.tool === "fetch_url" && (
        <div className="timeline-tool-body timeline-tool-content">
          <MarkdownContent className="markdown-body chat-markdown">
            {block.content}
          </MarkdownContent>
        </div>
      )}
      {open && block.summary && (
        (block.tool === "write_kb" || !block.sources?.length) &&
        block.tool !== "ask_user" && (
        <div className="timeline-tool-body">
          <div className="timeline-tool-summary">{block.summary}</div>
        </div>
        )
      )}
      {open &&
        block.tool === "ask_user" &&
        block.status === "done" &&
        block.question_id &&
        block.options &&
        block.options.length > 0 && (
          <div className="timeline-tool-body timeline-ask-user">
            <PendingQuestion
              question={{
                id: block.question_id,
                question: block.question || block.summary || "请选择",
                options: block.options as QuestionOption[],
                multi_select: block.multi_select,
              }}
              conversationId={conversationId}
              resolvedLabel={block.choice_resolved}
              onResolved={(result, choiceLabel) =>
                onQuestionResolved?.(block.id, result, choiceLabel)
              }
            />
          </div>
        )}
    </div>
  );
}

export function TimelineBlockView({
  block,
  cumulative,
  liveElapsedMs,
  inParallel,
  durationBold,
  onOpenSource,
  previewPath,
  conversationId,
  onQuestionResolved,
}: Props) {
  if (block.type === "tool") {
    return (
      <ToolBlockView
        block={block}
        liveElapsedMs={liveElapsedMs}
        durationBold={inParallel ? durationBold : true}
        onOpenSource={onOpenSource}
        previewPath={previewPath}
        conversationId={conversationId}
        onQuestionResolved={onQuestionResolved}
      />
    );
  }

  if (block.type === "parallel") {
    const maxMs = maxParallelDuration(block.children);
    return (
      <div className="timeline-parallel">
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
            cumulative={cumulative}
            liveElapsedMs={liveElapsedMs}
            inParallel
            durationBold={
              child.type === "tool" &&
              maxMs !== undefined &&
              child.duration_ms === maxMs
            }
            onOpenSource={onOpenSource}
            previewPath={previewPath}
            conversationId={conversationId}
            onQuestionResolved={onQuestionResolved}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="timeline-text">
      <MarkdownContent className="markdown-body chat-markdown">
        {block.content}
      </MarkdownContent>
    </div>
  );
}
