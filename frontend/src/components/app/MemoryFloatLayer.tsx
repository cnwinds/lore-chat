import { MemoryPanel } from "../memory/MemoryPanel";
import type { DocWidth } from "../../types/doc";

type Props = {
  docWidth?: DocWidth;
  onClose: () => void;
  onToggleWidth?: () => void;
  onOpenConversation?: (conversationId: string) => void;
  onAttentionChange?: () => void;
};

/** 记忆浮窗：贴在聊天区左缘，与媒体/文档浮窗同槽。 */
export function MemoryFloatLayer({
  docWidth = "wide",
  onClose,
  onToggleWidth,
  onOpenConversation,
  onAttentionChange,
}: Props) {
  return (
    <>
      <div className="doc-float-backdrop" aria-hidden onClick={onClose} />
      <div
        className="doc-float-panel"
        onClick={(e) => e.stopPropagation()}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <MemoryPanel
          docWidth={docWidth}
          onClose={onClose}
          onToggleWidth={onToggleWidth}
          onOpenConversation={onOpenConversation}
          onAttentionChange={onAttentionChange}
        />
      </div>
    </>
  );
}
