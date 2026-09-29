import { useCallback, useState } from "react";
import type { DocWidth } from "../../types/doc";
import { KnowledgeCardList } from "./KnowledgeCardList";

type Props = {
  scope: string;
  title: string;
  docWidth?: DocWidth;
  onClose: () => void;
  onToggleWidth?: () => void;
  onOpenConversation?: (conversationId: string) => void;
  onMutated?: () => void;
};

export function KnowledgeCardsPanel({
  scope,
  title,
  docWidth = "wide",
  onClose,
  onToggleWidth,
  onOpenConversation,
  onMutated,
}: Props) {
  const [refreshKey, setRefreshKey] = useState(0);
  const [count, setCount] = useState<number | null>(null);

  const handleCountChange = useCallback((n: number | null) => {
    setCount(n);
  }, []);

  const metaLabel =
    count === null
      ? null
      : count === 0
        ? "暂无条目"
        : `${count} 条`;

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
            onClick={() => setRefreshKey((k) => k + 1)}
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

      <div className="kb-float-meta">{metaLabel}</div>

      <div className="kb-float-body">
        <KnowledgeCardList
          scope={scope}
          refreshKey={refreshKey}
          onCountChange={handleCountChange}
          onOpenConversation={onOpenConversation}
          onMutated={onMutated}
        />
      </div>
    </div>
  );
}
