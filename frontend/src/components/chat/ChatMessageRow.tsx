import {
  computeCumulative,
  formatDuration,
  getMessageCopyText,
  downloadUrl,
  type ChatMessage,
  type IngestResult,
  type SourceRef,
} from "../../api";
import { formatMessageTs } from "../../utils/chatMessage";
import { MarkdownContent } from "../MarkdownContent";
import { ChatSources } from "../ChatSources";
import { CopyButton } from "../CopyButton";
import { TimelineBlockView } from "../TimelineBlockView";

export type ChatMessageRowProps = {
  message: ChatMessage;
  index: number;
  isLiveStreaming: boolean;
  liveElapsedMs: number;
  previewPath?: string | null;
  conversationId: string | null;
  onOpenSource: (src: SourceRef) => void;
  onQuestionResolved: (
    blockId: string,
    result: IngestResult,
    choiceLabel: string,
  ) => void;
};

function getMessageDuration(m: ChatMessage): number | undefined {
  if (m.total_duration_ms !== undefined) return m.total_duration_ms;
  if (!m.timeline?.length) return undefined;
  const { toolCumulative, parallelCumulative } = computeCumulative(m.timeline);
  let max = 0;
  for (const v of toolCumulative.values()) max = Math.max(max, v);
  for (const v of parallelCumulative.values()) max = Math.max(max, v);
  return max > 0 ? max : undefined;
}

function renderMessageMeta(
  m: ChatMessage,
  isLive: boolean,
  liveElapsedMs: number,
) {
  const copyText = getMessageCopyText(m);

  if (m.role === "user") {
    if (!copyText && !m.ts) return null;
    return (
      <div className="chat-meta chat-meta-user">
        {copyText && <CopyButton text={copyText} />}
        <span className="chat-meta-spacer" />
        {m.ts && <span>{formatMessageTs(m.ts)}</span>}
      </div>
    );
  }

  const durationMs = isLive ? liveElapsedMs : getMessageDuration(m);
  const timeStr = !isLive && m.ts ? formatMessageTs(m.ts) : null;
  if (!timeStr && (durationMs === undefined || durationMs <= 0) && !copyText) {
    return null;
  }

  return (
    <div className="chat-meta chat-meta-assistant">
      <div className="chat-meta-info">
        {timeStr && <span>{timeStr}</span>}
        {!isLive && durationMs !== undefined && durationMs > 0 && (
          <span>用时 {formatDuration(durationMs)}</span>
        )}
      </div>
      {copyText && !isLive && <CopyButton text={copyText} />}
    </div>
  );
}

function renderMessageContent(
  m: ChatMessage,
  isLive: boolean,
  liveElapsedMs: number,
  previewPath: string | null | undefined,
  conversationId: string | null,
  onOpenSource: (src: SourceRef) => void,
  onQuestionResolved: (
    blockId: string,
    result: IngestResult,
    choiceLabel: string,
  ) => void,
) {
  if (m.timeline && m.timeline.length > 0) {
    const cumulative = computeCumulative(m.timeline);
    return m.timeline.map((block, i) => (
      <TimelineBlockView
        key={
          block.type === "tool"
            ? block.id
            : block.type === "parallel"
              ? block.batch_id
              : `text-${i}`
        }
        block={block}
        cumulative={cumulative}
        liveElapsedMs={isLive ? liveElapsedMs : undefined}
        onOpenSource={onOpenSource}
        previewPath={previewPath}
        conversationId={conversationId}
        onQuestionResolved={onQuestionResolved}
      />
    ));
  }
  if (m.text) {
    if (m.role === "user") {
      return <div className="chat-user-text">{m.text}</div>;
    }
    return (
      <MarkdownContent className="markdown-body chat-markdown">
        {m.text}
      </MarkdownContent>
    );
  }
  return null;
}

export function messageHasBody(m: ChatMessage, isLive: boolean): boolean {
  if (m.role === "user") return true;
  if (m.timeline?.length) return true;
  if (m.text) return true;
  if (m.sources?.length) return true;
  if (m.attachments?.length) return true;
  if (isLive) return false;
  return !!(m.ts || getMessageDuration(m) || getMessageCopyText(m));
}

export function ChatMessageRow({
  message: m,
  index: _index,
  isLiveStreaming,
  liveElapsedMs,
  previewPath,
  conversationId,
  onOpenSource,
  onQuestionResolved,
}: ChatMessageRowProps) {
  return (
    <div
      className={`chat-row ${m.role === "user" ? "chat-row-user" : "chat-row-assistant"}`}
    >
      <div className={`chat-bubble chat-bubble-${m.role}`}>
        {renderMessageContent(
          m,
          isLiveStreaming,
          liveElapsedMs,
          previewPath,
          conversationId,
          onOpenSource,
          onQuestionResolved,
        )}
        {m.sources && m.sources.length > 0 && (
          <ChatSources
            sources={m.sources}
            previewPath={previewPath}
            onOpen={onOpenSource}
          />
        )}
        {m.attachments &&
          m.attachments.map((a) => (
            <div key={a}>
              <a href={downloadUrl(a)}>下载附件：{a.split("/").pop()}</a>
            </div>
          ))}
        {renderMessageMeta(m, isLiveStreaming, liveElapsedMs)}
      </div>
    </div>
  );
}
