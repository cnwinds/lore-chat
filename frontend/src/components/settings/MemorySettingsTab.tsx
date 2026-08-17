import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  confirmMemoryFact,
  editMemoryFact,
  forgetMemoryFact,
  listMemoryFacts,
  rejectMemoryFact,
  type MemoryFact,
} from "../../api";
import { useDismissOnOutsideClick } from "../../hooks/useDismissOnOutsideClick";
import {
  CheckIcon,
  DocIconBtn,
  EditIcon,
  MoreIcon,
  SaveIcon,
  TrashIcon,
  XIcon,
} from "../DocToolbarIcons";
import { SettingsAttentionDot } from "./SettingsAttentionDot";

type Props = {
  onOpenConversation?: (conversationId: string) => void;
  onAttentionChange?: () => void;
  onPendingCountChange?: (count: number) => void;
};

type MenuAction = {
  id: string;
  label: string;
  icon: ReactNode;
  danger?: boolean;
  onClick: () => void;
};

function MemoryFactMenu({
  actions,
  disabled,
}: {
  actions: MenuAction[];
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useDismissOnOutsideClick(rootRef, open, () => setOpen(false), {
    escape: true,
    pointerEvent: "mousedown",
  });

  if (actions.length === 0) return null;

  return (
    <div ref={rootRef} className="doc-overflow-anchor">
      <DocIconBtn
        label="更多操作"
        className="memory-fact-icon-btn"
        disabled={disabled}
        active={open}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <MoreIcon />
      </DocIconBtn>
      {open ? (
        <div className="doc-overflow-menu" role="menu" aria-label="记忆操作">
          {actions.map((action) => (
            <button
              key={action.id}
              type="button"
              role="menuitem"
              className={`doc-overflow-item${action.danger ? " doc-overflow-item--danger" : ""}`}
              disabled={disabled}
              title={action.label}
              onClick={() => {
                action.onClick();
                setOpen(false);
              }}
            >
              {action.icon}
              <span>{action.label}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function MemoryStatement({
  statement,
  conversationIds,
  disabled,
  onOpenConversation,
}: {
  statement: string;
  conversationIds: string[];
  disabled?: boolean;
  onOpenConversation?: (conversationId: string) => void;
}) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const canJump =
    Boolean(onOpenConversation) && conversationIds.length > 0 && !disabled;
  const multi = conversationIds.length > 1;

  useDismissOnOutsideClick(rootRef, pickerOpen, () => setPickerOpen(false), {
    escape: true,
    pointerEvent: "mousedown",
  });

  if (!canJump) {
    return <p className="memory-fact-statement">{statement}</p>;
  }

  function openOne(cid: string) {
    onOpenConversation?.(cid);
    setPickerOpen(false);
  }

  return (
    <div ref={rootRef} className="memory-fact-statement-anchor">
      <button
        type="button"
        className="memory-fact-statement memory-fact-statement--jump"
        title={multi ? "选择来源会话" : "打开来源会话"}
        aria-label={multi ? "选择来源会话" : "打开来源会话"}
        aria-expanded={multi ? pickerOpen : undefined}
        aria-haspopup={multi ? "menu" : undefined}
        onClick={() => {
          if (!multi) {
            openOne(conversationIds[0]);
            return;
          }
          setPickerOpen((v) => !v);
        }}
      >
        {statement}
      </button>
      {pickerOpen && multi ? (
        <div className="doc-overflow-menu" role="menu" aria-label="来源会话">
          {conversationIds.map((cid) => (
            <button
              key={cid}
              type="button"
              role="menuitem"
              className="doc-overflow-item"
              title={cid}
              aria-label={`打开来源会话 ${cid}`}
              onClick={() => openOne(cid)}
            >
              会话 {cid.length > 8 ? `${cid.slice(0, 8)}…` : cid}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function buildActions(
  fact: MemoryFact,
  onEdit: () => void,
  onConfirm: () => void,
  onReject: () => void,
  onForget: () => void,
): MenuAction[] {
  if (fact.status === "candidate") {
    return [
      {
        id: "confirm",
        label: "确认",
        icon: <CheckIcon size={14} />,
        onClick: onConfirm,
      },
      {
        id: "reject",
        label: "拒绝",
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

export function MemorySettingsTab({
  onOpenConversation,
  onAttentionChange,
  onPendingCountChange,
}: Props) {
  const [facts, setFacts] = useState<MemoryFact[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listMemoryFacts();
      const next = data.facts || [];
      setFacts(next);
      onPendingCountChange?.(
        next.filter((f) => f.status === "candidate").length,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载记忆失败");
    } finally {
      setLoading(false);
    }
  }, [onPendingCountChange]);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(factId: string, fn: () => Promise<unknown>) {
    setBusyId(factId);
    setError(null);
    try {
      await fn();
      await load();
      onAttentionChange?.();
      setEditingId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setBusyId(null);
    }
  }

  if (loading && facts.length === 0) {
    return <p className="settings-panel-hint">加载记忆…</p>;
  }

  return (
    <div
      className="settings-tab-panel"
      role="tabpanel"
      id="settings-panel-memory"
      aria-labelledby="settings-tab-memory"
    >
      <p className="settings-tab-hint">
        已确认与待确认的长期画像。待确认可晋升或拒绝；已确认可编辑或遗忘。点击记忆正文可跳转到来源会话。
      </p>
      {error ? <p className="settings-panel-error">{error}</p> : null}
      {facts.length === 0 ? (
        <p className="settings-panel-hint">暂无记忆条目。</p>
      ) : (
        <ul className="memory-fact-list">
          {facts.map((f) => {
            const busy = busyId === f.id;
            const editing = editingId === f.id;
            const candidate = f.status === "candidate";
            const conversationIds = f.conversation_ids || [];
            return (
              <li
                key={f.id}
                className={`memory-fact-item${candidate ? " memory-fact-item--candidate" : ""}`}
                title={f.slot_key}
              >
                <div className="memory-fact-main">
                  {candidate ? (
                    <span className="memory-fact-status memory-fact-status--candidate">
                      <SettingsAttentionDot title="待确认" />
                      待确认
                    </span>
                  ) : null}
                  {editing ? (
                    <textarea
                      className="memory-fact-edit"
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      rows={Math.max(3, draft.split("\n").length)}
                      disabled={busy}
                      aria-label="编辑记忆内容"
                    />
                  ) : (
                    <MemoryStatement
                      statement={f.statement}
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
                        onClick={() => void run(f.id, () => editMemoryFact(f.id, draft.trim()))}
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
                      disabled={busy}
                      actions={buildActions(
                        f,
                        () => {
                          setEditingId(f.id);
                          setDraft(f.statement);
                        },
                        () => void run(f.id, () => confirmMemoryFact(f.id)),
                        () => {
                          if (window.confirm("确定拒绝这条待确认记忆？")) {
                            void run(f.id, () => rejectMemoryFact(f.id));
                          }
                        },
                        () => {
                          if (window.confirm("确定遗忘这条记忆？")) {
                            void run(f.id, () => forgetMemoryFact(f.id));
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
      )}
      <div className="settings-form-footer">
        <button type="button" className="settings-btn" onClick={() => void load()} disabled={loading}>
          刷新
        </button>
      </div>
    </div>
  );
}
