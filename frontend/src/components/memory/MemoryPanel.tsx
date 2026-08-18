import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  confirmMemoryFact,
  editMemoryFact,
  forgetMemoryFact,
  listMemoryFacts,
  rejectMemoryFact,
  type MemoryFact,
} from "../../api";
import type { DocWidth } from "../../types/doc";
import { FixedOverflowMenu } from "../FixedOverflowMenu";
import {
  CheckIcon,
  DocIconBtn,
  EditIcon,
  MoreIcon,
  SaveIcon,
  TrashIcon,
  XIcon,
} from "../DocToolbarIcons";
import { SettingsAttentionDot } from "../settings/SettingsAttentionDot";
import { useDemoCapability } from "../../hooks/useDemoCapability";

type Props = {
  docWidth?: DocWidth;
  onClose: () => void;
  onToggleWidth?: () => void;
  onOpenConversation?: (conversationId: string) => void;
  onAttentionChange?: () => void;
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
      <FixedOverflowMenu
        open={open}
        anchorRef={rootRef}
        align="end"
        label="记忆操作"
        onDismiss={() => setOpen(false)}
      >
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
      </FixedOverflowMenu>
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
      {multi ? (
        <FixedOverflowMenu
          open={pickerOpen}
          anchorRef={rootRef}
          align="start"
          label="来源会话"
          onDismiss={() => setPickerOpen(false)}
        >
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
        </FixedOverflowMenu>
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

/**
 * 长期画像内容：由浮窗层承载，头栏与媒体图库同构。
 */
export function MemoryPanel({
  docWidth = "wide",
  onClose,
  onToggleWidth,
  onOpenConversation,
  onAttentionChange,
}: Props) {
  const { canWrite } = useDemoCapability();
  const [facts, setFacts] = useState<MemoryFact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listMemoryFacts();
      setFacts(data.facts || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载记忆失败");
    } finally {
      setLoading(false);
    }
  }, []);

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

  const pendingCount = facts.filter((f) => f.status === "candidate").length;
  const confirmedCount = facts.length - pendingCount;
  const metaLabel = loading
    ? "加载中…"
    : error
      ? null
      : facts.length === 0
        ? "暂无条目"
        : `${confirmedCount} 条已确认${
            pendingCount > 0 ? ` · ${pendingCount} 条待确认` : ""
          }`;

  return (
    <div
      className={`kb-float-panel kb-float-panel--${docWidth}`}
      aria-label="长期画像"
    >
      <header className="kb-float-header">
        <div className="kb-float-header-main">
          <div className="kb-float-kicker">记忆</div>
          <h2 className="kb-float-title">长期画像</h2>
          <nav className="kb-float-crumb" aria-label="路径">
            <span className="kb-float-crumb-seg">
              <span className="is-current">记忆</span>
            </span>
          </nav>
        </div>
        <div className="kb-float-header-actions">
          <button
            type="button"
            className="doc-icon-btn"
            title="刷新"
            aria-label="刷新"
            disabled={loading}
            onClick={() => void load()}
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
        {error ? <div className="kb-float-error">错误：{error}</div> : null}
        {!loading && !error && facts.length === 0 ? (
          <div className="kb-float-empty">
            <div className="kb-float-empty-mark" aria-hidden />
            <p>暂无记忆条目</p>
            <p className="kb-float-empty-hint">
              对话中稳定归属主人的画像会在此出现
            </p>
          </div>
        ) : null}
        {facts.length > 0 ? (
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
                    {canWrite && editing ? (
                      <>
                        <DocIconBtn
                          label="保存"
                          className="memory-fact-icon-btn"
                          disabled={busy || !draft.trim()}
                          onClick={() =>
                            void run(f.id, () => editMemoryFact(f.id, draft.trim()))
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
                    ) : null}
                    {canWrite && !editing ? (
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
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
