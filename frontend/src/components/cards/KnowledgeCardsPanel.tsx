import { useState } from "react";
import type { DocWidth } from "../../types/doc";
import { KnowledgeCardsTabs } from "./KnowledgeCardsTabs";

type Props = {
  scope: string;
  title: string;
  docWidth?: DocWidth;
  refreshKey?: number;
  onClose: () => void;
  onToggleWidth?: () => void;
  onOpenConversation?: (conversationId: string) => void;
  onMutated?: () => void;
  onUseProposal?: (text: string) => void;
};

export function KnowledgeCardsPanel({
  scope,
  title,
  docWidth = "wide",
  refreshKey: externalRefreshKey = 0,
  onClose,
  onToggleWidth,
  onOpenConversation,
  onMutated,
  onUseProposal,
}: Props) {
  const [localRefreshKey, setLocalRefreshKey] = useState(0);

  const effectiveRefreshKey = externalRefreshKey + localRefreshKey;

  return (
    <div
      className={`kb-float-panel kb-float-panel--${docWidth}`}
      aria-label={`知识卡 · ${title}`}
    >
      <header className="kb-float-header">
        <div className="kb-float-header-main">
          <h2 className="kb-float-title">知识卡 · {title}</h2>
        </div>
        <div className="kb-float-header-actions">
          <button
            type="button"
            className="doc-icon-btn"
            title="刷新"
            aria-label="刷新"
            onClick={() => setLocalRefreshKey((k) => k + 1)}
          >
            ↻
          </button>
          {onToggleWidth ? (
            <button
              type="button"
              className="doc-icon-btn"
              title={docWidth === "wide" ? "变窄" : "变宽"}
              onClick={onToggleWidth}
            >
              {docWidth === "wide" ? "⟧" : "⟦"}
            </button>
          ) : null}
          <button
            type="button"
            className="doc-icon-btn"
            title="关闭"
            aria-label="关闭"
            onClick={onClose}
          >
            ×
          </button>
        </div>
      </header>

      <KnowledgeCardsTabs
        variant="float"
        scope={scope}
        refreshKey={effectiveRefreshKey}
        onOpenConversation={onOpenConversation}
        onMutated={onMutated}
        onUseProposal={onUseProposal}
      />
    </div>
  );
}
