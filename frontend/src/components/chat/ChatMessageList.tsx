import type { MutableRefObject, RefObject } from "react";
import { formatDuration, type ChatMessage, type IngestResult, type SourceRef } from "../../api";
import { expandMessagesForDisplay } from "../../utils/chatMessage";
import { ChatMessageRow, messageHasBody } from "./ChatMessageRow";
import { ConversationOutline } from "./ConversationOutline";

export type ChatMessageListProps = {
  msgs: ChatMessage[];
  loadingHistory: boolean;
  streaming: boolean;
  liveElapsedMs: number;
  streamNowMs?: number;
  streamingAssistantIdxRef: MutableRefObject<number | null>;
  messagesContainerRef: RefObject<HTMLDivElement | null>;
  messagesEndRef: RefObject<HTMLDivElement | null>;
  previewPath?: string | null;
  conversationId: string | null;
  onOpenSource: (src: SourceRef) => void;
  onQuestionResolved: (
    blockId: string,
    result: IngestResult,
    choiceLabel: string,
  ) => void;
};

export function ChatMessageList({
  msgs,
  loadingHistory,
  streaming,
  liveElapsedMs,
  streamNowMs,
  streamingAssistantIdxRef,
  messagesContainerRef,
  messagesEndRef,
  previewPath,
  conversationId,
  onOpenSource,
  onQuestionResolved,
}: ChatMessageListProps) {
  const rows = expandMessagesForDisplay(msgs);

  return (
    <>
      <div className="chat-messages-shell">
        <div className="chat-messages" ref={messagesContainerRef}>
          <div className="chat-messages-inner">
            {loadingHistory && <div className="chat-empty">加载对话中…</div>}
            {!loadingHistory && msgs.length === 0 && (
              <div className="chat-empty">
                直接输入即可。Agent 会自动检索知识库、搜索网页并整理到知识库。
              </div>
            )}
            {rows.map((row) => {
              const isLiveStreaming =
                streaming &&
                row.isTailSlice &&
                streamingAssistantIdxRef.current === row.sourceIndex;
              if (!messageHasBody(row.message, isLiveStreaming)) {
                return null;
              }
              return (
                <ChatMessageRow
                  key={row.key}
                  message={row.message}
                  isLiveStreaming={isLiveStreaming}
                  liveElapsedMs={liveElapsedMs}
                  streamNowMs={streamNowMs}
                  previewPath={previewPath}
                  conversationId={conversationId}
                  onOpenSource={onOpenSource}
                  onQuestionResolved={onQuestionResolved}
                />
              );
            })}
            <div
              ref={messagesEndRef}
              className="chat-messages-anchor"
              aria-hidden
            />
          </div>
        </div>
        <ConversationOutline
          msgs={msgs}
          conversationId={conversationId}
          scrollRootRef={messagesContainerRef}
        />
      </div>
      {streaming && (
        <div className="chat-streaming-wrap">
          <div className="chat-streaming-bar">
            <span className="chat-streaming-label">思考中…</span>
            {liveElapsedMs > 0 && (
              <span className="chat-streaming-duration">
                用时 {formatDuration(liveElapsedMs)}
              </span>
            )}
          </div>
        </div>
      )}
    </>
  );
}
