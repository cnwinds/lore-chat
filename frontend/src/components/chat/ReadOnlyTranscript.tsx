import { type RefObject } from "react";
import type { ChatMessage } from "../../api";
import { ChatMessageList } from "./ChatMessageList";
import type { TranscriptOutlineLayout } from "./ConversationTranscriptPanel";

type Props = {
  msgs: ChatMessage[];
  messagesContainerRef: RefObject<HTMLDivElement | null>;
  messagesEndRef: RefObject<HTMLDivElement | null>;
  outlineLayout?: TranscriptOutlineLayout;
  className?: string;
};

/** 只读消息区，供分享页等场景复用 Chat 同款渲染。 */
export function ReadOnlyTranscript({
  msgs,
  messagesContainerRef,
  messagesEndRef,
  outlineLayout = "rail",
  className,
}: Props) {
  const noop = () => {};
  return (
    <div className={className}>
      <ChatMessageList
        msgs={msgs}
        loadingHistory={false}
        streaming={false}
        liveElapsedMs={0}
        streamingAssistantIdxRef={{ current: null }}
        messagesContainerRef={messagesContainerRef}
        messagesEndRef={messagesEndRef}
        conversationId={null}
        onOpenSource={noop}
        onQuestionResolved={noop}
        readOnly
        showOutline
        outlineLayout={outlineLayout}
      />
    </div>
  );
}
