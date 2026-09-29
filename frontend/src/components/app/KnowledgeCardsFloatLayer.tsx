import { KnowledgeCardsPanel } from "../cards/KnowledgeCardsPanel";
import type { DocWidth } from "../../types/doc";
import { KbFloatLayer } from "./KbFloatLayer";

type Props = {
  scope: string;
  title: string;
  docWidth?: DocWidth;
  onClose: () => void;
  onToggleWidth?: () => void;
  onOpenConversation?: (conversationId: string) => void;
  onMutated?: () => void;
};

/** 知识卡浮窗：贴在聊天区左缘，与记忆/媒体/文档浮窗同槽。 */
export function KnowledgeCardsFloatLayer({
  scope,
  title,
  docWidth = "wide",
  onClose,
  onToggleWidth,
  onOpenConversation,
  onMutated,
}: Props) {
  return (
    <KbFloatLayer onClose={onClose}>
      <KnowledgeCardsPanel
        scope={scope}
        title={title}
        docWidth={docWidth}
        onClose={onClose}
        onToggleWidth={onToggleWidth}
        onOpenConversation={onOpenConversation}
        onMutated={onMutated}
      />
    </KbFloatLayer>
  );
}
