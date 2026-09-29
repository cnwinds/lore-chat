import { useCallback, useEffect, useState } from "react";
import {
  confirmCard,
  editCard,
  forgetCard,
  listCards,
  rejectCard,
  type KnowledgeCard,
} from "../../api";
import {
  CheckIcon,
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
  onOpenConversation?: (conversationId: string) => void;
  onMutated?: () => void;
};

function buildCardActions(
  card: KnowledgeCard,
  onEdit: () => void,
  onConfirm: () => void,
  onReject: () => void,
  onForget: () => void,
): MemoryFactMenuAction[] {
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

export function KnowledgeCardList({
  scope,
  refreshKey = 0,
  onCountChange,
  onOpenConversation,
  onMutated,
}: Props) {
  const [cards, setCards] = useState<KnowledgeCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listCards(scope);
      setCards(data.cards || []);
      onCountChange?.(data.count ?? (data.cards || []).length);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载知识卡失败");
      onCountChange?.(null);
    } finally {
      setLoading(false);
    }
  }, [scope, onCountChange]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

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

  return (
    <>
      {error ? <div className="kb-float-error">错误：{error}</div> : null}
      {!loading && !error && cards.length === 0 ? (
        <div className="kb-float-empty">
          <div className="kb-float-empty-mark" aria-hidden />
          <p>还没有知识卡。和这个角色多聊几次，它会自己积累。</p>
        </div>
      ) : null}
      {cards.length > 0 ? (
        <ul className="memory-fact-list">
          {cards.map((c) => {
            const busy = busyId === c.id;
            const editing = editingId === c.id;
            const candidate = c.status === "candidate";
            const conversationIds = c.conversation_ids || [];
            return (
              <li
                key={c.id}
                className={`memory-fact-item${candidate ? " memory-fact-item--candidate" : ""}`}
                title={c.slot_key}
              >
                <div className="memory-fact-main">
                  <div className="knowledge-card-tags">
                    <span className="knowledge-card-kind">
                      {CARD_KIND_LABELS[c.kind]}
                    </span>
                    {c.external ? (
                      <span className="knowledge-card-external">外部</span>
                    ) : null}
                    {candidate ? (
                      <span className="memory-fact-status memory-fact-status--candidate knowledge-card-pending">
                        待印证
                      </span>
                    ) : null}
                  </div>
                  {editing ? (
                    <textarea
                      className="memory-fact-edit"
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      rows={Math.max(3, draft.split("\n").length)}
                      disabled={busy}
                      aria-label="编辑知识卡内容"
                    />
                  ) : (
                    <MemoryStatement
                      statement={c.statement}
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
                        onClick={() =>
                          void run(c.id, () =>
                            editCard(scope, c.id, draft.trim()),
                          )
                        }
                      >
                        <SaveIcon />
                      </DocIconBtn>
                      <DocIconBtn
                        label="取消"
                        className="memory-fact-icon-btn"
                        disabled={busy}
                        onClick={() => setEditingId(null)}
                      >
                        <XIcon />
                      </DocIconBtn>
                    </>
                  ) : (
                    <MemoryFactMenu
                      label="知识卡操作"
                      disabled={busy}
                      actions={buildCardActions(
                        c,
                        () => {
                          setEditingId(c.id);
                          setDraft(c.statement);
                        },
                        () => void run(c.id, () => confirmCard(scope, c.id)),
                        () => {
                          if (window.confirm("确定驳回这条待印证知识卡？")) {
                            void run(c.id, () => rejectCard(scope, c.id));
                          }
                        },
                        () => {
                          if (window.confirm("确定遗忘这条知识卡？")) {
                            void run(c.id, () => forgetCard(scope, c.id));
                          }
                        },
                      )}
                    />
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
    </>
  );
}
