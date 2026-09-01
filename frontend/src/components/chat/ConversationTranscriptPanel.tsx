import { type MutableRefObject, type RefObject } from "react";
import type { ChatMessage, IngestResult, SourceRef } from "../../api";
import type { MemoryEventNotice } from "../../hooks/chat/useConversationMemoryEvents";
import { ChatMessageList } from "./ChatMessageList";

export type TranscriptOutlineLayout = "rail" | "sheet";

type Props = {
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
  onOpenConversation?: (target: {
    conversationId: string;
    messageId?: string;
  }) => void;
  onQuestionResolved: (
    blockId: string,
    result: IngestResult,
    choiceLabel: string,
  ) => void;
  onRetryReply?: (assistantSourceIndex: number) => void;
  outlineLayout?: TranscriptOutlineLayout;
  memoryNotice?: MemoryEventNotice | null;
  onDismissMemoryNotice?: () => void;
};

/** 会话消息区：列表 + 可选记忆提示。 */
export function ConversationTranscriptPanel({
  msgs,
  loadingHistory,
  streaming,
  reconciling,
  networkReconnectNeeded,
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
  outlineLayout = "rail",
  memoryNotice,
  onDismissMemoryNotice,
}: Props) {
  return (
    <>
      {memoryNotice && (
        <div className="chat-memory-notice" role="status">
          <span>{memoryNotice.label}</span>
          <button
            type="button"
            className="chat-memory-notice-dismiss"
            onClick={onDismissMemoryNotice}
            aria-label="关闭"
          >
            ×
          </button>
        </div>
      )}
      <ChatMessageList
        msgs={msgs}
        loadingHistory={loadingHistory}
        streaming={streaming}
        reconciling={reconciling}
        networkReconnectNeeded={networkReconnectNeeded}
        onNetworkReconnect={onNetworkReconnect}
        liveElapsedMs={liveElapsedMs}
        streamNowMs={streamNowMs}
        streamingAssistantIdxRef={streamingAssistantIdxRef}
        messagesContainerRef={messagesContainerRef}
        messagesEndRef={messagesEndRef}
        previewPath={previewPath}
        conversationId={conversationId}
        onOpenSource={onOpenSource}
        onOpenConversation={onOpenConversation}
        onQuestionResolved={onQuestionResolved}
        onRetryReply={onRetryReply}
        outlineLayout={outlineLayout}
      />
    </>
  );
}
