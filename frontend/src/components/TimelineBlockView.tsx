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
import { SandboxTerminal } from "./SandboxTerminal";
import { SourceChip } from "./SourceChip";
import { MessageRangeHighlight } from "./chat/MessageRangeHighlight";
import { isNoiseProgressLine } from "../utils/progressLog";

type Props = {
  block: TimelineBlock;
  cumulative: CumulativeInfo;
  liveElapsedMs?: number;
  isLive?: boolean;
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
  textHighlight?: { start: number; end: number };
};

/** 折叠时单行摘要：工具类型 + 关键结果 */
function toolOneLiner(block: Extract<TimelineBlock, { type: "tool" }>): string | undefined {
  if (block.status === "running") {
    if (block.progress_log?.length) {
      for (let i = block.progress_log.length - 1; i >= 0; i--) {
        const line = (block.progress_log[i] || "").trim();
        if (line && !isNoiseProgressLine(line)) return line;
      }
    }
    return block.query || "执行中…";
  }
  if (block.status === "interrupted") {
    return block.summary || "连接中断，未完成";
  }
  if (block.tool === "ask_user" || (block.tool === "sandbox_run" && block.question_id)) {
    if (block.choice_resolved) return `已选择：${block.choice_resolved}`;
    return block.question || block.summary;
  }
  if (block.tool === "sandbox_run" && block.query) {
    const cmd =
      block.query.length > 80 ? `${block.query.slice(0, 80)}…` : block.query;
    if (block.summary) {
      const s =
        block.summary.length > 60
          ? `${block.summary.slice(0, 60)}…`
          : block.summary;
      return `$ ${cmd} · ${s}`;
    }
    return `$ ${cmd}`;
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
  if (block.tool === "edit_doc" && block.summary) {
    const mode = block.reindex_mode ? ` · ${block.reindex_mode}` : "";
    return `${block.summary}${mode}`;
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
  // 检索/搜索/打开链接默认折叠；其余工具在流式或执行中默认展开。
  // 未作答的征询始终展开，方便用户直接选择。
  const isLive = liveElapsedMs !== undefined;
  const pendingAsk =
    (block.tool === "ask_user" || block.tool === "sandbox_run") &&
    block.status === "done" &&
    !block.choice_resolved &&
    !!block.question_id &&
    Array.isArray(block.options) &&
    block.options.length > 0;
  const collapsedByDefault =
    block.tool === "search_kb" ||
    block.tool === "web_search" ||
    block.tool === "fetch_url";
  const defaultOpen =
    !collapsedByDefault &&
    (isLive ||
      pendingAsk ||
      block.status === "running" ||
      (block.tool === "sandbox_run" &&
        !block.question_id &&
        (!!block.query || !!block.progress_log?.length)));
  // 用户显式点过则以其选择为准，否则用默认值。
  // 展开状态用组件内 state 维护，随组件卸载自动回收（不跨会话泄漏）。
  const [override, setOverride] = useState<boolean | null>(null);
  const open = override ?? defaultOpen;

  function toggleOpen() {
    setOverride(!open);
  }

  const oneLiner = toolOneLiner(block);
  const displayMs =
    block.status === "running" && liveElapsedMs !== undefined
      ? liveElapsedMs
      : block.duration_ms;

  function handleOpenSource(src: SourceRef) {
    if (
      block.tool === "edit_doc" &&
      block.preview &&
      src.type === "kb" &&
      src.path
    ) {
      const excerpt = block.preview.trim().slice(0, 120);
      onOpenSource({ ...src, excerpt });
      return;
    }
    onOpenSource(src);
  }

  const statusIcon =
    block.status === "running" ? "⏳" : block.status === "interrupted" ? "⚠" : "✓";

  return (
    <div className={`timeline-tool timeline-tool-${block.status}`}>
      <button
        type="button"
        className={`timeline-tool-header${open ? "" : " timeline-tool-header-collapsed"}`}
        onClick={toggleOpen}
        aria-expanded={open}
        title={!open && oneLiner ? `${block.label}  ${oneLiner}` : undefined}
      >
        <span className="timeline-tool-label">
          <span className="timeline-tool-name">
            {statusIcon} {block.label}
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
        block.tool === "sandbox_run" &&
        !block.question_id &&
        (!!block.query || !!block.progress_log?.length || block.status === "running") && (
          <div className="timeline-tool-body">
            <SandboxTerminal block={block} live={isLive || block.status === "running"} />
          </div>
        )}
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
              onOpen={handleOpenSource}
            />
          ))}
        </div>
      )}
      {open &&
        block.tool !== "sandbox_run" &&
        block.progress_log &&
        block.progress_log.length > 0 && (
        <div className="timeline-tool-body timeline-tool-progress">
          <pre className="timeline-tool-progress-log">
            {block.progress_log.join("\n")}
          </pre>
        </div>
      )}
      {open && block.content && block.tool === "fetch_url" && (
        <div className="timeline-tool-body timeline-tool-content">
          <MarkdownContent className="markdown-body chat-markdown">
            {block.content}
          </MarkdownContent>
        </div>
      )}
      {open &&
        block.summary &&
        !(block.progress_log && block.progress_log.length > 0) &&
        block.tool !== "sandbox_run" &&
        (block.tool === "write_kb" ||
          block.tool === "edit_doc" ||
          !block.sources?.length) &&
        block.tool !== "ask_user" && (
          <div className="timeline-tool-body">
            <div className="timeline-tool-summary">{block.summary}</div>
          </div>
        )}
      {open && block.status === "interrupted" && !block.summary && (
        <div className="timeline-tool-body">
          <div className="timeline-tool-summary">连接中断，未完成</div>
        </div>
      )}
      {open && block.tool === "edit_doc" && block.preview && (
        <div className="timeline-tool-body timeline-tool-patch-preview">
          <div className="timeline-tool-patch-label">修改预览</div>
          <pre className="timeline-tool-patch-text">{block.preview}</pre>
        </div>
      )}
      {open &&
        (block.tool === "ask_user" || block.tool === "sandbox_run") &&
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

function ThinkBlockView({
  block,
  isLive,
}: {
  block: Extract<TimelineBlock, { type: "think" }>;
  isLive?: boolean;
}) {
  const [open, setOpen] = useState(!!isLive);
  const preview =
    block.content.length > 120
      ? `${block.content.slice(0, 120).trim()}…`
      : block.content.trim();

  return (
    <div className="timeline-think">
      <button
        type="button"
        className={`timeline-think-header${open ? "" : " timeline-think-header-collapsed"}`}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="timeline-think-label">思考过程</span>
        {!open && preview ? (
          <span className="timeline-think-oneline">{preview}</span>
        ) : null}
        <span className="timeline-think-chevron">{open ? "▾" : "▸"}</span>
      </button>
      {open ? (
        <div className="timeline-think-body">
          <MarkdownContent className="markdown-body chat-markdown timeline-think-markdown">
            {block.content}
          </MarkdownContent>
        </div>
      ) : null}
    </div>
  );
}

export function TimelineBlockView({
  block,
  cumulative,
  liveElapsedMs,
  isLive,
  inParallel,
  durationBold,
  onOpenSource,
  previewPath,
  conversationId,
  onQuestionResolved,
  textHighlight,
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
                  : child.type === "think"
                    ? `think-${i}`
                    : child.type === "user_inject"
                      ? `inject-${child.inject_id}`
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
            textHighlight={textHighlight}
          />
        ))}
      </div>
    );
  }

  if (block.type === "think") {
    return <ThinkBlockView block={block} isLive={isLive} />;
  }

  if (block.type === "user_inject") {
    // Shown as a standalone user bubble via expandMessagesForDisplay.
    return null;
  }

  if (block.type === "text") {
    return (
      <div className="timeline-text">
        {textHighlight ? (
          <div className="chat-markdown">
            <MessageRangeHighlight
              text={block.content}
              start={textHighlight.start}
              end={textHighlight.end}
            />
          </div>
        ) : (
          <MarkdownContent className="markdown-body chat-markdown">
            {block.content}
          </MarkdownContent>
        )}
      </div>
    );
  }

  return null;
}
