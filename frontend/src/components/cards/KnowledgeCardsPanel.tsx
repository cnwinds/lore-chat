import { useCallback, useState } from "react";
import type { DocWidth } from "../../types/doc";
import { CardGrowthTimeline } from "./CardGrowthTimeline";
import { KnowledgeCardList } from "./KnowledgeCardList";

type PanelTab = "cards" | "growth";

type Props = {
  scope: string;
  title: string;
  docWidth?: DocWidth;
  refreshKey?: number;
  onClose: () => void;
  onToggleWidth?: () => void;
  onOpenConversation?: (conversationId: string) => void;
  onMutated?: () => void;
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
}: Props) {
  const [localRefreshKey, setLocalRefreshKey] = useState(0);
  const [tab, setTab] = useState<PanelTab>("cards");
  const [cardCount, setCardCount] = useState<number | null>(null);
  const [fadedCount, setFadedCount] = useState<number | null>(null);
  const [growthCount, setGrowthCount] = useState<number | null>(null);

  const effectiveRefreshKey = externalRefreshKey + localRefreshKey;

  const handleCardCountChange = useCallback((n: number | null) => {
    setCardCount(n);
  }, []);

  const handleFadedCountChange = useCallback((n: number | null) => {
    setFadedCount(n);
  }, []);

  const handleGrowthCountChange = useCallback((n: number | null) => {
    setGrowthCount(n);
  }, []);

  const metaLabel =
    tab === "cards"
      ? cardCount === null
        ? null
        : cardCount === 0 && (fadedCount ?? 0) === 0
          ? "暂无条目"
          : [
              `${cardCount} 条`,
              fadedCount && fadedCount > 0 ? `已淡出 ${fadedCount}` : null,
            ]
              .filter(Boolean)
              .join(" · ")
      : growthCount === null
        ? null
        : growthCount === 0
          ? "暂无记录"
          : `${growthCount} 条记录`;

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

      <div
        className="kb-float-tabs"
        role="tablist"
        aria-label="知识卡页签"
      >
        {(
          [
            { id: "cards" as const, label: "卡片" },
            { id: "growth" as const, label: "成长" },
          ] as const
        ).map((item) => {
          const pressed = tab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={pressed}
              aria-pressed={pressed}
              className={`settings-tab${pressed ? " settings-tab--active" : ""}`}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          );
        })}
      </div>

      <div className="kb-float-meta">{metaLabel}</div>

      <div className="kb-float-body">
        {tab === "cards" ? (
          <KnowledgeCardList
            scope={scope}
            refreshKey={effectiveRefreshKey}
            onCountChange={handleCardCountChange}
            onFadedCountChange={handleFadedCountChange}
            onOpenConversation={onOpenConversation}
            onMutated={onMutated}
          />
        ) : (
          <CardGrowthTimeline
            scope={scope}
            refreshKey={effectiveRefreshKey}
            onCountChange={handleGrowthCountChange}
            onOpenConversation={onOpenConversation}
          />
        )}
      </div>
    </div>
  );
}
