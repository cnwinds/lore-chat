import { useCallback, useEffect, useState } from "react";
import {
  acceptCardProposal,
  dismissCardProposal,
  listCardGrowth,
  type CardGrowthEntry,
  type CardGrowthItem,
  type CardGrowthPersonaItem,
  type CardGrowthProposalItem,
} from "../../api";
import { formatMessageTime } from "../../utils/displayTime";
import { growthKindLabel } from "./cardKindLabels";
import {
  CARD_GROWTH_ACTION_LABELS,
  CARD_GROWTH_ENTRY_LABELS,
  cardGrowthSourcesLabel,
} from "./cardGrowthLabels";
import { personaRevisionSourceLabel } from "./personaRevisionLabels";

type Props = {
  scope: string;
  refreshKey?: number;
  onCountChange?: (count: number | null) => void;
  onOpenConversation?: (conversationId: string) => void;
  onOpenPersonaHistory?: () => void;
  onUseProposal?: (text: string) => void;
  onMutated?: () => void;
};

function GrowthCardItemRow({ item }: { item: CardGrowthItem }) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const sources = item.sources || [];
  const showSources = sources.length > 0;

  return (
    <div className="card-growth-item">
      <div className="card-growth-item-head">
        <span className="card-growth-action">
          {CARD_GROWTH_ACTION_LABELS[item.action]}
        </span>
        {growthKindLabel(item.kind) ? (
          <span className="card-growth-kind">{growthKindLabel(item.kind)}</span>
        ) : null}
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

function GrowthPersonaItemRow({
  item,
  onOpenPersonaHistory,
}: {
  item: CardGrowthPersonaItem;
  onOpenPersonaHistory?: () => void;
}) {
  if (item.action === "rolled_back") {
    const sourceLabel = personaRevisionSourceLabel(item.source);
    return (
      <div className="card-growth-item">
        <p className="card-growth-statement">
          回退了一次{sourceLabel}改动
        </p>
      </div>
    );
  }

  return (
    <div className="card-growth-item">
      <p className="card-growth-statement">{item.reason}</p>
      {item.before ? (
        <p className="card-growth-previous card-growth-persona-before">
          {item.before}
        </p>
      ) : null}
      {item.after ? (
        <p className="card-growth-persona-after">{item.after}</p>
      ) : null}
      {item.basis.length > 0 ? (
        <GrowthBasisList basis={item.basis} />
      ) : null}
      {onOpenPersonaHistory ? (
        <button
          type="button"
          className="card-growth-sources-toggle"
          onClick={onOpenPersonaHistory}
        >
          在人设历史里查看
        </button>
      ) : null}
    </div>
  );
}

function GrowthBasisList({ basis }: { basis: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="card-growth-sources">
      <button
        type="button"
        className="card-growth-sources-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "收起依据" : `依据（${basis.length}）`}
      </button>
      {open ? (
        <ul className="card-growth-sources-list">
          {basis.map((text, i) => (
            <li key={i}>{text}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function GrowthProposalItemRow({
  item,
  scope,
  onUseProposal,
  onAfterDecision,
}: {
  item: CardGrowthProposalItem;
  scope: string;
  onUseProposal?: (text: string) => void;
  onAfterDecision: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const headline =
    item.target === "skill"
      ? `提议固化为 Skill「${item.title}」`
      : `提议写成文档「${item.title}」`;

  async function handleAccept() {
    if (!onUseProposal) return;
    setBusy(true);
    setError(null);
    try {
      const result = await acceptCardProposal(scope, item.proposal_id);
      onUseProposal(result.request_text);
      onAfterDecision();
    } catch (err) {
      setError(err instanceof Error ? err.message : "接受提议失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleDismiss() {
    setBusy(true);
    setError(null);
    try {
      await dismissCardProposal(scope, item.proposal_id);
      onAfterDecision();
    } catch (err) {
      setError(err instanceof Error ? err.message : "忽略提议失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card-growth-item">
      <p className="card-growth-statement">{headline}</p>
      <p className="card-growth-previous">{item.reason}</p>
      {item.basis.length > 0 ? <GrowthBasisList basis={item.basis} /> : null}
      <div className="card-growth-proposal-actions">
        {item.status === "pending" ? (
          <>
            {onUseProposal ? (
              <button
                type="button"
                className="card-growth-proposal-btn"
                disabled={busy}
                onClick={() => void handleAccept()}
              >
                接受
              </button>
            ) : null}
            <button
              type="button"
              className="card-growth-proposal-btn card-growth-proposal-btn--muted"
              disabled={busy}
              onClick={() => void handleDismiss()}
            >
              忽略
            </button>
          </>
        ) : item.status === "accepted" ? (
          <span className="card-growth-proposal-status">已接受</span>
        ) : (
          <span className="card-growth-proposal-status">已忽略</span>
        )}
      </div>
      {error ? <p className="persona-history-row-error">{error}</p> : null}
    </div>
  );
}

function GrowthEntryRow({
  entry,
  scope,
  onOpenConversation,
  onOpenPersonaHistory,
  onUseProposal,
  onAfterDecision,
}: {
  entry: CardGrowthEntry;
  scope: string;
  onOpenConversation?: (conversationId: string) => void;
  onOpenPersonaHistory?: () => void;
  onUseProposal?: (text: string) => void;
  onAfterDecision: () => void;
}) {
  const hasConversation = Boolean(entry.conversation_id);
  const conversationDisabled =
    !hasConversation || entry.conversation_title === null;

  return (
    <article className="card-growth-entry">
      <header className="card-growth-entry-head">
        <span
          className={`card-growth-entry-kind card-growth-entry-kind--${entry.kind}`}
        >
          {CARD_GROWTH_ENTRY_LABELS[entry.kind]}
        </span>
        <time className="card-growth-entry-time" dateTime={entry.created_at}>
          {formatMessageTime(entry.created_at)}
        </time>
        {entry.kind === "learned" && hasConversation ? (
          onOpenConversation ? (
            <button
              type="button"
              className="card-growth-conversation-btn"
              disabled={conversationDisabled}
              onClick={() => {
                if (entry.conversation_id) {
                  onOpenConversation(entry.conversation_id);
                }
              }}
            >
              {entry.conversation_title || "来源会话"}
            </button>
          ) : (
            <span className="card-growth-conversation-label">
              {entry.conversation_title || "来源会话"}
            </span>
          )
        ) : null}
      </header>
      <div className="card-growth-entry-items">
        {entry.kind === "persona"
          ? entry.items.map((item, index) => (
              <GrowthPersonaItemRow
                key={`${entry.id}-persona-${index}`}
                item={item}
                onOpenPersonaHistory={onOpenPersonaHistory}
              />
            ))
          : entry.kind === "proposal"
            ? entry.items.map((item, index) => (
                <GrowthProposalItemRow
                  key={`${entry.id}-proposal-${index}`}
                  item={item}
                  scope={scope}
                  onUseProposal={onUseProposal}
                  onAfterDecision={onAfterDecision}
                />
              ))
            : entry.items.map((item, index) => (
                <GrowthCardItemRow
                  key={`${entry.id}-${item.card_id}-${index}`}
                  item={item}
                />
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
  onOpenPersonaHistory,
  onUseProposal,
  onMutated,
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

  const handleAfterDecision = useCallback(() => {
    void load();
    onMutated?.();
  }, [load, onMutated]);

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
            scope={scope}
            onOpenConversation={onOpenConversation}
            onOpenPersonaHistory={onOpenPersonaHistory}
            onUseProposal={onUseProposal}
            onAfterDecision={handleAfterDecision}
          />
        ))}
      </div>
    </>
  );
}
