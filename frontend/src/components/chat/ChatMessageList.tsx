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
  reconciling?: boolean;
  networkReconnectNeeded?: boolean;
  onNetworkReconnect?: () => void;
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
  readOnly?: boolean;
  /** 只读场景（如公开分享页）仍展示提问导航 */
  showOutline?: boolean;
  /** 提问导航布局：rail 桌面浮条；sheet 手机底部抽屉 */
  outlineLayout?: "rail" | "sheet";
};

export function ChatMessageList({
  msgs,
  loadingHistory,
  streaming,
  reconciling = false,
  networkReconnectNeeded = false,
  onNetworkReconnect,
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
  readOnly = false,
  showOutline = false,
  outlineLayout = "rail",
}: ChatMessageListProps) {
  const rows = expandMessagesForDisplay(msgs);
  const showWelcome = !loadingHistory && msgs.length === 0;

  return (
    <>
      <div className="chat-messages-shell">
        {showWelcome && (
          <div className="chat-welcome">
            <LoreLogo variant="wordmark" className="chat-welcome-logo" />
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
                !readOnly &&
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
                  onOpenConversation={readOnly ? undefined : onOpenConversation}
                  onQuestionResolved={onQuestionResolved}
                  readOnly={readOnly}
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
        {(!readOnly || showOutline) && (
          <ConversationOutline
            msgs={msgs}
            conversationId={conversationId}
            scrollRootRef={messagesContainerRef}
            layout={outlineLayout}
          />
        )}
      </div>
      {reconciling && !streaming && (
        <div className="chat-streaming-wrap">
          <div className="chat-streaming-bar chat-streaming-bar--reconcile">
            <span className="chat-streaming-label">连接中断，正在同步服务器…</span>
          </div>
        </div>
      )}
      {networkReconnectNeeded && !streaming && !reconciling && (
        <div className="chat-streaming-wrap">
          <div className="chat-streaming-bar chat-streaming-bar--reconcile">
            <span className="chat-streaming-label">
              网络不可达，无法同步服务器
            </span>
            {onNetworkReconnect && (
              <button
                type="button"
                className="chat-retry-btn"
                onClick={onNetworkReconnect}
              >
                重新连接
              </button>
            )}
          </div>
        </div>
      )}
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
