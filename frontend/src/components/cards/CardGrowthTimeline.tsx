import { useCallback, useEffect, useState } from "react";
import {
  listCardGrowth,
  type CardGrowthEntry,
  type CardGrowthItem,
} from "../../api";
import { formatMessageTime } from "../../utils/displayTime";
import { CARD_KIND_LABELS } from "./cardKindLabels";
import {
  CARD_GROWTH_ACTION_LABELS,
  CARD_GROWTH_ENTRY_LABELS,
  cardGrowthSourcesLabel,
} from "./cardGrowthLabels";

type Props = {
  scope: string;
  refreshKey?: number;
  onCountChange?: (count: number | null) => void;
  onOpenConversation?: (conversationId: string) => void;
};

function GrowthItemRow({ item }: { item: CardGrowthItem }) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const sources = item.sources || [];
  const showSources = sources.length > 0;

  return (
    <div className="card-growth-item">
      <div className="card-growth-item-head">
        <span className="card-growth-action">
          {CARD_GROWTH_ACTION_LABELS[item.action]}
        </span>
        <span className="card-growth-kind">{CARD_KIND_LABELS[item.kind]}</span>
        {item.external ? (
          <span className="knowledge-card-external">外部</span>
        ) : null}
      </div>
      <p className="card-growth-statement">{item.statement}</p>
      {item.previous ? (
        <p className="card-growth-previous">原：{item.previous}</p>
      ) : null}
      {showSources ? (
        <div className="card-growth-sources">
          <button
            type="button"
            className="card-growth-sources-toggle"
            aria-expanded={sourcesOpen}
            onClick={() => setSourcesOpen((v) => !v)}
          >
            {cardGrowthSourcesLabel(item.action, sources.length)}
          </button>
          {sourcesOpen ? (
            <ul className="card-growth-sources-list">
              {sources.map((source) => (
                <li key={source.card_id}>{source.statement}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function GrowthEntryRow({
  entry,
  onOpenConversation,
}: {
  entry: CardGrowthEntry;
  onOpenConversation?: (conversationId: string) => void;
}) {
  const hasConversation = Boolean(entry.conversation_id);
  const conversationDisabled =
    !hasConversation || entry.conversation_title === null;

  return (
    <article className="card-growth-entry">
      <header className="card-growth-entry-head">
        <span className={`card-growth-entry-kind card-growth-entry-kind--${entry.kind}`}>
          {CARD_GROWTH_ENTRY_LABELS[entry.kind]}
        </span>
        <time className="card-growth-entry-time" dateTime={entry.created_at}>
          {formatMessageTime(entry.created_at)}
        </time>
        {entry.kind === "learned" && hasConversation ? (
          <button
            type="button"
            className="card-growth-conversation-btn"
            disabled={conversationDisabled}
            onClick={() => {
              if (entry.conversation_id) onOpenConversation?.(entry.conversation_id);
            }}
          >
            {entry.conversation_title || "来源会话"}
          </button>
        ) : null}
      </header>
      <div className="card-growth-entry-items">
        {entry.items.map((item, index) => (
          <GrowthItemRow key={`${entry.id}-${item.card_id}-${index}`} item={item} />
        ))}
      </div>
    </article>
  );
}

export function CardGrowthTimeline({
  scope,
  refreshKey = 0,
  onCountChange,
  onOpenConversation,
}: Props) {
  const [entries, setEntries] = useState<CardGrowthEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listCardGrowth(scope);
      const next = data.entries || [];
      setEntries(next);
      onCountChange?.(next.length);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载成长记录失败");
      onCountChange?.(null);
    } finally {
      setLoading(false);
    }
  }, [scope, onCountChange]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  if (loading && entries.length === 0 && !error) {
    return <p className="channel-panel-muted">加载中…</p>;
  }

  if (!loading && !error && entries.length === 0) {
    return (
      <div className="kb-float-empty">
        <div className="kb-float-empty-mark" aria-hidden />
        <p>还没有成长记录。卡片被学到、整理或淡出时会记在这里。</p>
      </div>
    );
  }

  return (
    <>
      {error ? <div className="kb-float-error">错误：{error}</div> : null}
      <div className="card-growth-timeline">
        {entries.map((entry) => (
          <GrowthEntryRow
            key={entry.id}
            entry={entry}
            onOpenConversation={onOpenConversation}
          />
        ))}
      </div>
    </>
  );
}
