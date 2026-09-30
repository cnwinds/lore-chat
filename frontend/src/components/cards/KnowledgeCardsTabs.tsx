import { useCallback, useState } from "react";
import { CardGrowthTimeline } from "./CardGrowthTimeline";
import { KnowledgeCardList } from "./KnowledgeCardList";
import { PersonaHistoryList } from "./PersonaHistoryList";

type PanelTab = "cards" | "growth" | "history";

type Props = {
  scope: string;
  refreshKey?: number;
  variant: "float" | "inline";
  onOpenConversation?: (conversationId: string) => void;
  onMutated?: () => void;
  onUseProposal?: (text: string) => void;
};

export function KnowledgeCardsTabs({
  scope,
  refreshKey = 0,
  variant,
  onOpenConversation,
  onMutated,
  onUseProposal,
}: Props) {
  const [tab, setTab] = useState<PanelTab>("cards");
  const [cardCount, setCardCount] = useState<number | null>(null);
  const [fadedCount, setFadedCount] = useState<number | null>(null);
  const [growthCount, setGrowthCount] = useState<number | null>(null);
  const [historyCount, setHistoryCount] = useState<number | null>(null);

  const handleCardCountChange = useCallback((n: number | null) => {
    setCardCount(n);
  }, []);

  const handleFadedCountChange = useCallback((n: number | null) => {
    setFadedCount(n);
  }, []);

  const handleGrowthCountChange = useCallback((n: number | null) => {
    setGrowthCount(n);
  }, []);

  const handleHistoryCountChange = useCallback((n: number | null) => {
    setHistoryCount(n);
  }, []);

  const openPersonaHistory = useCallback(() => {
    setTab("history");
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
      : tab === "growth"
        ? growthCount === null
          ? null
          : growthCount === 0
            ? "暂无记录"
            : `${growthCount} 条记录`
        : historyCount === null
          ? null
          : historyCount === 0
            ? "暂无记录"
            : `${historyCount} 个版本`;

  const tabsClass =
    variant === "float" ? "kb-float-tabs" : "card-tabs-inline";
  const metaClass =
    variant === "float" ? "kb-float-meta" : "card-tabs-inline-meta";
  const bodyClass =
    variant === "float" ? "kb-float-body" : "card-tabs-inline-body";

  return (
    <>
      <div className={tabsClass} role="tablist" aria-label="知识卡页签">
        {(
          [
            { id: "cards" as const, label: "卡片" },
            { id: "growth" as const, label: "成长" },
            { id: "history" as const, label: "人设历史" },
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

      <div className={metaClass}>{metaLabel}</div>

      <div className={bodyClass}>
        {tab === "cards" ? (
          <KnowledgeCardList
            scope={scope}
            refreshKey={refreshKey}
            onCountChange={handleCardCountChange}
            onFadedCountChange={handleFadedCountChange}
            onOpenConversation={onOpenConversation}
            onMutated={onMutated}
          />
        ) : tab === "growth" ? (
          <CardGrowthTimeline
            scope={scope}
            refreshKey={refreshKey}
            onCountChange={handleGrowthCountChange}
            onOpenConversation={onOpenConversation}
            onOpenPersonaHistory={openPersonaHistory}
            onUseProposal={onUseProposal}
            onMutated={onMutated}
          />
        ) : (
          <PersonaHistoryList
            scope={scope}
            refreshKey={refreshKey}
            onCountChange={handleHistoryCountChange}
            onMutated={onMutated}
          />
        )}
      </div>
    </>
  );
}
