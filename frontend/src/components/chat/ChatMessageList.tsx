import type { MutableRefObject, RefObject } from "react";
import { formatDuration, type ChatMessage, type IngestResult, type SourceRef } from "../../api";
import { expandMessagesForDisplay, canRetryAssistantReply, findPrecedingUserForRetry } from "../../utils/chatMessage";
import type { ConversationLinkTarget } from "../../utils/conversationLinks";
import { LoreLogo } from "../LoreLogo";
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
  onOpenConversation?: (target: ConversationLinkTarget) => void;
  onQuestionResolved: (
    blockId: string,
    result: IngestResult,
    choiceLabel: string,
  ) => void;
  onRetryReply?: (assistantSourceIndex: number) => void;
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
  onOpenConversation,
  onQuestionResolved,
  onRetryReply,
}: ChatMessageListProps) {
  const rows = expandMessagesForDisplay(msgs);
  const showWelcome = !loadingHistory && msgs.length === 0;

  return (
    <>
      <div className="chat-messages-shell">
        {showWelcome && (
          <div className="chat-welcome">
            <LoreLogo className="chat-welcome-logo" />
          </div>
        )}
        <div className="chat-messages" ref={messagesContainerRef}>
          <div className="chat-messages-inner">
            {loadingHistory && <div className="chat-empty">加载对话中…</div>}
            {rows.map((row) => {
              const isLiveStreaming =
                streaming &&
                row.isTailSlice &&
                streamingAssistantIdxRef.current === row.sourceIndex;
              if (!messageHasBody(row.message, isLiveStreaming)) {
                return null;
              }
              const preceding = findPrecedingUserForRetry(msgs, row.sourceIndex);
              const precedingRetryable =
                !!preceding &&
                (!!(preceding.text || "").trim() ||
                  !!(preceding.attachments && preceding.attachments.length));
              const canRetry =
                row.isTailSlice &&
                !isLiveStreaming &&
                canRetryAssistantReply(row.message) &&
                precedingRetryable &&
                !!onRetryReply;
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
                  onOpenConversation={onOpenConversation}
                  onQuestionResolved={onQuestionResolved}
                  onRetryReply={
                    canRetry
                      ? () => onRetryReply(row.sourceIndex)
                      : undefined
                  }
                  retryDisabled={streaming}
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
