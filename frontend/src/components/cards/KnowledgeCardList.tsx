import { useCallback, useEffect, useMemo, useState } from "react";
import {
  confirmCard,
  editCard,
  forgetCard,
  listCards,
  rejectCard,
  restoreCard,
  type KnowledgeCard,
} from "../../api";
import {
  CheckIcon,
  DiscardIcon,
  DocIconBtn,
  EditIcon,
  SaveIcon,
  TrashIcon,
  XIcon,
} from "../DocToolbarIcons";
import {
  MemoryFactMenu,
  MemoryStatement,
  type MemoryFactMenuAction,
} from "../memory/MemoryFactParts";
import { CARD_KIND_LABELS } from "./cardKindLabels";

type Props = {
  scope: string;
  refreshKey?: number;
  onCountChange?: (count: number | null) => void;
  onFadedCountChange?: (count: number | null) => void;
  onOpenConversation?: (conversationId: string) => void;
  onMutated?: () => void;
};

function buildCardActions(
  card: KnowledgeCard,
  onEdit: () => void,
  onConfirm: () => void,
  onReject: () => void,
  onForget: () => void,
  onRestore: () => void,
): MemoryFactMenuAction[] {
  if (card.status === "stale") {
    return [
      {
        id: "restore",
        label: "恢复",
        icon: <DiscardIcon size={14} />,
        onClick: onRestore,
      },
      {
        id: "forget",
        label: "遗忘",
        icon: <TrashIcon size={14} />,
        danger: true,
        onClick: onForget,
      },
    ];
  }
  if (card.status === "candidate") {
    return [
      {
        id: "confirm",
        label: "确认",
        icon: <CheckIcon size={14} />,
        onClick: onConfirm,
      },
      {
        id: "reject",
        label: "驳回",
        icon: <XIcon size={14} />,
        danger: true,
        onClick: onReject,
      },
    ];
  }
  return [
    {
      id: "edit",
      label: "编辑",
      icon: <EditIcon size={14} />,
      onClick: onEdit,
    },
    {
      id: "forget",
      label: "遗忘",
      icon: <TrashIcon size={14} />,
      danger: true,
      onClick: onForget,
    },
  ];
}

function KnowledgeCardRow({
  card,
  busy,
  editing,
  draft,
  onDraftChange,
  onEditStart,
  onEditCancel,
  onSave,
  onOpenConversation,
  onConfirm,
  onReject,
  onForget,
  onRestore,
}: {
  card: KnowledgeCard;
  busy: boolean;
  editing: boolean;
  draft: string;
  onDraftChange: (value: string) => void;
  onEditStart: () => void;
  onEditCancel: () => void;
  onSave: () => void;
  onOpenConversation?: (conversationId: string) => void;
  onConfirm: () => void;
  onReject: () => void;
  onForget: () => void;
  onRestore: () => void;
}) {
  const candidate = card.status === "candidate";
  const stale = card.status === "stale";
  const conversationIds = card.conversation_ids || [];

  return (
    <li
      className={`memory-fact-item${
        candidate ? " memory-fact-item--candidate" : ""
      }${stale ? " memory-fact-item--stale" : ""}`}
      title={card.slot_key}
    >
      <div className="memory-fact-main">
        <div className="knowledge-card-tags">
          <span className="knowledge-card-kind">
            {CARD_KIND_LABELS[card.kind]}
          </span>
          {card.external ? (
            <span className="knowledge-card-external">外部</span>
          ) : null}
          {candidate ? (
            <span className="memory-fact-status memory-fact-status--candidate knowledge-card-pending">
              待印证
            </span>
          ) : null}
          {stale ? (
            <span className="knowledge-card-stale">已淡出</span>
          ) : null}
        </div>
        {editing ? (
          <textarea
            className="memory-fact-edit"
            value={draft}
            onChange={(e) => onDraftChange(e.target.value)}
            rows={Math.max(3, draft.split("\n").length)}
            disabled={busy}
            aria-label="编辑知识卡内容"
          />
        ) : (
          <MemoryStatement
            statement={card.statement}
            conversationIds={conversationIds}
            disabled={busy}
            onOpenConversation={onOpenConversation}
          />
        )}
      </div>
      <div className="memory-fact-actions">
        {editing ? (
          <>
            <DocIconBtn
              label="保存"
              className="memory-fact-icon-btn"
              disabled={busy || !draft.trim()}
              onClick={onSave}
            >
              <SaveIcon />
            </DocIconBtn>
            <DocIconBtn
              label="取消"
              className="memory-fact-icon-btn"
              disabled={busy}
              onClick={onEditCancel}
            >
              <XIcon />
            </DocIconBtn>
          </>
        ) : (
          <MemoryFactMenu
            label="知识卡操作"
            disabled={busy}
            actions={buildCardActions(
              card,
              onEditStart,
              onConfirm,
              onReject,
              onForget,
              onRestore,
            )}
          />
        )}
      </div>
    </li>
  );
}

export function KnowledgeCardList({
  scope,
  refreshKey = 0,
  onCountChange,
  onFadedCountChange,
  onOpenConversation,
  onMutated,
}: Props) {
  const [cards, setCards] = useState<KnowledgeCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [staleExpanded, setStaleExpanded] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listCards(scope);
      setCards(data.cards || []);
      onCountChange?.(data.count ?? 0);
      onFadedCountChange?.(data.faded_count ?? 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载知识卡失败");
      onCountChange?.(null);
      onFadedCountChange?.(null);
    } finally {
      setLoading(false);
    }
  }, [scope, onCountChange, onFadedCountChange]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const { activeCards, staleCards } = useMemo(() => {
    const active: KnowledgeCard[] = [];
    const stale: KnowledgeCard[] = [];
    for (const card of cards) {
      if (card.status === "stale") stale.push(card);
      else active.push(card);
    }
    return { activeCards: active, staleCards: stale };
  }, [cards]);

  async function run(cardId: string, fn: () => Promise<unknown>) {
    setBusyId(cardId);
    setError(null);
    try {
      await fn();
      await load();
      onMutated?.();
      setEditingId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setBusyId(null);
    }
  }

  if (loading && cards.length === 0 && !error) {
    return <p className="channel-panel-muted">加载中…</p>;
  }

  const showEmpty = !loading && !error && activeCards.length === 0 && staleCards.length === 0;

  return (
    <>
      {error ? <div className="kb-float-error">错误：{error}</div> : null}
      {showEmpty ? (
        <div className="kb-float-empty">
          <div className="kb-float-empty-mark" aria-hidden />
          <p>还没有知识卡。和这个角色多聊几次，它会自己积累。</p>
        </div>
      ) : null}
      {activeCards.length > 0 ? (
        <ul className="memory-fact-list">
          {activeCards.map((c) => (
            <KnowledgeCardRow
              key={c.id}
              card={c}
              busy={busyId === c.id}
              editing={editingId === c.id}
              draft={draft}
              onDraftChange={setDraft}
              onEditStart={() => {
                setEditingId(c.id);
                setDraft(c.statement);
              }}
              onEditCancel={() => setEditingId(null)}
              onSave={() =>
                void run(c.id, () => editCard(scope, c.id, draft.trim()))
              }
              onOpenConversation={onOpenConversation}
              onConfirm={() => void run(c.id, () => confirmCard(scope, c.id))}
              onReject={() => {
                if (window.confirm("确定驳回这条待印证知识卡？")) {
                  void run(c.id, () => rejectCard(scope, c.id));
                }
              }}
              onForget={() => {
                if (window.confirm("确定遗忘这条知识卡？")) {
                  void run(c.id, () => forgetCard(scope, c.id));
                }
              }}
              onRestore={() => void run(c.id, () => restoreCard(scope, c.id))}
            />
          ))}
        </ul>
      ) : null}
      {staleCards.length > 0 ? (
        <div className="knowledge-card-stale-group">
          <button
            type="button"
            className="knowledge-card-stale-toggle"
            aria-expanded={staleExpanded}
            onClick={() => setStaleExpanded((v) => !v)}
          >
            已淡出 · {staleCards.length}
          </button>
          {staleExpanded ? (
            <ul className="memory-fact-list knowledge-card-stale-list">
              {staleCards.map((c) => (
                <KnowledgeCardRow
                  key={c.id}
                  card={c}
                  busy={busyId === c.id}
                  editing={false}
                  draft=""
                  onDraftChange={() => undefined}
                  onEditStart={() => undefined}
                  onEditCancel={() => undefined}
                  onSave={() => undefined}
                  onOpenConversation={onOpenConversation}
                  onConfirm={() => undefined}
                  onReject={() => undefined}
                  onForget={() => {
                    if (window.confirm("确定遗忘这条知识卡？")) {
                      void run(c.id, () => forgetCard(scope, c.id));
                    }
                  }}
                  onRestore={() => void run(c.id, () => restoreCard(scope, c.id))}
                />
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </>
  );
}
