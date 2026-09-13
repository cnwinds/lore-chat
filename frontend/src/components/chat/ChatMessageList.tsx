import type { MutableRefObject, RefObject } from "react";
import { formatDuration, type ChatMessage, type IngestResult, type SourceRef } from "../../api";
import {
  expandMessagesForDisplay,
  canRetryAssistantReply,
  findPrecedingUserForRetry,
} from "../../utils/chatMessage";
import type { ConversationLinkTarget } from "../../utils/conversationLinks";
import type { TimelineSegmentView } from "../../hooks/chat/useRoleTimeline";
import { chatTranscriptChrome } from "../../utils/chatTranscriptChrome";
import { LoreLogo } from "../LoreLogo";
import { ChatMessageRow, messageHasBody } from "./ChatMessageRow";
import { ConversationOutline } from "./ConversationOutline";
import { TimelineSeparator } from "./TimelineSeparator";
import { RoomInterjectBar } from "./RoomInterjectBar";

const EMPTY_HISTORICAL: TimelineSegmentView[] = [];

export type ChatMessageListProps = {
  msgs: ChatMessage[];
  /** 角色时间线：tip 之前的只读段（旧→新） */
  historicalSegments?: TimelineSegmentView[];
  continuityIdleHours?: number;
  timelineHasMore?: boolean;
  loadingOlder?: boolean;
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
  roles?: { id: string; name: string }[];
  onRoomInterjectSent?: () => void;
};

function renderSegmentRows(opts: {
  msgs: ChatMessage[];
  conversationId: string | null;
  isTip: boolean;
  streaming: boolean;
  readOnly: boolean;
  liveElapsedMs: number;
  streamNowMs?: number;
  streamingAssistantIdxRef: MutableRefObject<number | null>;
  previewPath?: string | null;
  onOpenSource: (src: SourceRef) => void;
  onOpenConversation?: (target: ConversationLinkTarget) => void;
  onQuestionResolved: ChatMessageListProps["onQuestionResolved"];
  onRetryReply?: (assistantSourceIndex: number) => void;
}) {
  const {
    msgs,
    conversationId,
    isTip,
    streaming,
    readOnly,
    liveElapsedMs,
    streamNowMs,
    streamingAssistantIdxRef,
    previewPath,
    onOpenSource,
    onOpenConversation,
    onQuestionResolved,
    onRetryReply,
  } = opts;
  const rows = expandMessagesForDisplay(msgs);
  return rows.map((row) => {
    const isLiveStreaming =
      isTip &&
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
      isTip &&
      !readOnly &&
      row.isTailSlice &&
      !isLiveStreaming &&
      canRetryAssistantReply(row.message) &&
      precedingRetryable &&
      !!onRetryReply;
    return (
      <ChatMessageRow
        key={`${conversationId || "seg"}:${row.key}`}
        message={row.message}
        isLiveStreaming={isLiveStreaming}
        liveElapsedMs={liveElapsedMs}
        streamNowMs={streamNowMs}
        previewPath={previewPath}
        conversationId={conversationId}
        onOpenSource={onOpenSource}
        onOpenConversation={readOnly || !isTip ? onOpenConversation : onOpenConversation}
        onQuestionResolved={onQuestionResolved}
        readOnly={readOnly || !isTip}
        onRetryReply={
          canRetry ? () => onRetryReply!(row.sourceIndex) : undefined
        }
        retryDisabled={streaming}
      />
    );
  });
}

export function ChatMessageList({
  msgs,
  historicalSegments = EMPTY_HISTORICAL,
  continuityIdleHours = 6,
  timelineHasMore = false,
  loadingOlder = false,
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
  roles = [],
  onRoomInterjectSent,
}: ChatMessageListProps) {
  const hasHistory = historicalSegments.some((s) => s.messages.length > 0);
  const tipHasBody = expandMessagesForDisplay(msgs).some((row) =>
    messageHasBody(row.message, false),
  );
  const { showWelcome, showWelcomeLoading, showLoadOlderHint } =
    chatTranscriptChrome({
      loadingHistory,
      hasHistory,
      tipHasBody,
      streaming,
      timelineHasMore,
      loadingOlder,
    });

  const showTipSeparator = hasHistory && (tipHasBody || streaming);

  return (
    <>
      <div className="chat-messages-shell">
        {showWelcome && (
          <div
            className="chat-welcome"
            role={showWelcomeLoading ? "status" : undefined}
          >
            <LoreLogo variant="wordmark" className="chat-welcome-logo" />
            {showWelcomeLoading && (
              <div className="chat-welcome-status">加载对话中…</div>
            )}
          </div>
        )}
        <div className="chat-messages" ref={messagesContainerRef}>
          <div
            className={
              showWelcome
                ? "chat-messages-inner chat-messages-inner--fill"
                : "chat-messages-inner"
            }
          >
            {showLoadOlderHint && (
              <div className="chat-timeline-load-older" aria-live="polite">
                {loadingOlder ? "加载更早对话…" : "向上滚动加载更早对话"}
              </div>
            )}
            {historicalSegments.map((seg, i) => (
              <div
                key={seg.jumped ? `jump:${seg.conversationId}` : seg.conversationId}
                className="chat-timeline-segment"
                data-conversation-id={seg.conversationId}
                data-jumped={seg.jumped ? "true" : undefined}
              >
                {(i > 0 || seg.kind === "peer_dm" || seg.kind === "group") && (
                  <TimelineSeparator
                    idleHours={continuityIdleHours}
                    label={
                      seg.kind === "peer_dm"
                        ? "角色协作 · 共享房间"
                        : seg.kind === "group"
                          ? "群聊"
                          : undefined
                    }
                  />
                )}
                {renderSegmentRows({
                  msgs: seg.messages,
                  conversationId: seg.conversationId,
                  isTip: false,
                  streaming: false,
                  readOnly: true,
                  liveElapsedMs: 0,
                  streamingAssistantIdxRef,
                  previewPath,
                  onOpenSource,
                  onOpenConversation,
                  onQuestionResolved,
                })}
                {(seg.kind === "peer_dm" || seg.kind === "group") &&
                roles.length > 0 ? (
                  <RoomInterjectBar
                    roomId={seg.conversationId}
                    roles={roles}
                    kind={seg.kind}
                    onSent={onRoomInterjectSent}
                  />
                ) : null}
              </div>
            ))}
            {(showTipSeparator || tipHasBody || streaming) && (
              <div
                className="chat-timeline-segment chat-timeline-segment--tip"
                data-conversation-id={conversationId || undefined}
              >
                {showTipSeparator && (
                  <TimelineSeparator
                    idleHours={continuityIdleHours}
                    label={
                      historicalSegments.some((s) => s.jumped)
                        ? "定位到搜索结果 · 中间消息未加载"
                        : undefined
                    }
                  />
                )}
                {renderSegmentRows({
                  msgs,
                  conversationId,
                  isTip: true,
                  streaming,
                  readOnly,
                  liveElapsedMs,
                  streamNowMs,
                  streamingAssistantIdxRef,
                  previewPath,
                  onOpenSource,
                  onOpenConversation,
                  onQuestionResolved,
                  onRetryReply,
                })}
              </div>
            )}
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
            historicalSegments={historicalSegments}
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
