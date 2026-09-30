import { useCallback, useEffect, useMemo, useState } from "react";
import {
  confirmMemoryFact,
  editMemoryFact,
  forgetMemoryFact,
  listMemoryFacts,
  OWNER_GROWTH_SCOPE,
  rejectMemoryFact,
  restoreMemoryFact,
  type MemoryFact,
} from "../../api";
import type { DocWidth } from "../../types/doc";
import {
  CheckIcon,
  DocIconBtn,
  EditIcon,
  SaveIcon,
  TrashIcon,
  XIcon,
} from "../DocToolbarIcons";
import { SettingsAttentionDot } from "../settings/SettingsAttentionDot";
import { CardGrowthTimeline } from "../cards/CardGrowthTimeline";
import {
  MemoryFactMenu,
  MemoryStatement,
  type MemoryFactMenuAction,
} from "./MemoryFactParts";

type PanelTab = "memory" | "growth";

type Props = {
  docWidth?: DocWidth;
  onClose: () => void;
  onToggleWidth?: () => void;
  onOpenConversation?: (conversationId: string) => void;
  onAttentionChange?: () => void;
};

function buildActions(
  fact: MemoryFact,
  onEdit: () => void,
  onConfirm: () => void,
  onReject: () => void,
  onForget: () => void,
  onRestore?: () => void,
): MemoryFactMenuAction[] {
  if (fact.status === "stale") {
    const actions: MemoryFactMenuAction[] = [];
    if (onRestore) {
      actions.push({
        id: "restore",
        label: "恢复",
        icon: <CheckIcon size={14} />,
        onClick: onRestore,
      });
    }
    actions.push({
      id: "forget",
      label: "遗忘",
      icon: <TrashIcon size={14} />,
      danger: true,
      onClick: onForget,
    });
    return actions;
  }
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

function MemoryFactRow({
  fact,
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
  fact: MemoryFact;
  busy: boolean;
  editing: boolean;
  draft: string;
  onDraftChange: (v: string) => void;
  onEditStart: () => void;
  onEditCancel: () => void;
  onSave: () => void;
  onOpenConversation?: (conversationId: string) => void;
  onConfirm: () => void;
  onReject: () => void;
  onForget: () => void;
  onRestore?: () => void;
}) {
  const candidate = fact.status === "candidate";
  const stale = fact.status === "stale";
  const conversationIds = fact.conversation_ids || [];

  return (
    <li
      className={`memory-fact-item${candidate ? " memory-fact-item--candidate" : ""}${stale ? " memory-fact-item--stale" : ""}`}
      title={fact.slot_key}
    >
      <div className="memory-fact-main">
        {candidate ? (
          <span className="memory-fact-status memory-fact-status--candidate">
            <SettingsAttentionDot title="待确认" />
            待确认
          </span>
        ) : null}
        {stale ? <span className="knowledge-card-stale">已淡出</span> : null}
        {editing ? (
          <textarea
            className="memory-fact-edit"
            value={draft}
            onChange={(e) => onDraftChange(e.target.value)}
            rows={Math.max(3, draft.split("\n").length)}
            disabled={busy}
            aria-label="编辑记忆内容"
          />
        ) : (
          <MemoryStatement
            statement={fact.statement}
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
            disabled={busy}
            actions={buildActions(
              fact,
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
  const [tab, setTab] = useState<PanelTab>("memory");
  const [facts, setFacts] = useState<MemoryFact[]>([]);
  const [staleFacts, setStaleFacts] = useState<MemoryFact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [staleExpanded, setStaleExpanded] = useState(false);
  const [growthCount, setGrowthCount] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listMemoryFacts();
      setFacts(data.facts || []);
      setStaleFacts(data.stale || []);
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

  const pendingCount = useMemo(
    () => facts.filter((f) => f.status === "candidate").length,
    [facts],
  );
  const confirmedCount = facts.length - pendingCount;

  const memoryMetaLabel =
    tab === "memory"
      ? loading
        ? "加载中…"
        : error
          ? null
          : facts.length === 0 && staleFacts.length === 0
            ? "暂无条目"
            : [
                facts.length === 0
                  ? null
                  : `${confirmedCount} 条已确认${
                      pendingCount > 0 ? ` · ${pendingCount} 条待确认` : ""
                    }`,
                staleFacts.length > 0 ? `已淡出 ${staleFacts.length}` : null,
              ]
                .filter(Boolean)
                .join(" · ")
      : growthCount === null
        ? null
        : growthCount === 0
          ? "暂无记录"
          : `${growthCount} 条记录`;

  const showMemoryEmpty =
    !loading && !error && facts.length === 0 && staleFacts.length === 0;

  return (
    <div
      className={`kb-float-panel kb-float-panel--${docWidth}`}
      aria-label="记忆"
    >
      <header className="kb-float-header">
        <div className="kb-float-header-main">
          <h2 className="kb-float-title">记忆</h2>
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

      <div className="kb-float-tabs" role="tablist" aria-label="记忆页签">
        {(
          [
            { id: "memory" as const, label: "记忆" },
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

      <div className="kb-float-meta">{memoryMetaLabel}</div>

      <div className="kb-float-body">
        {tab === "growth" ? (
          <CardGrowthTimeline
            scope={OWNER_GROWTH_SCOPE}
            onCountChange={setGrowthCount}
            onOpenConversation={onOpenConversation}
          />
        ) : (
          <>
            {error ? <div className="kb-float-error">错误：{error}</div> : null}
            {showMemoryEmpty ? (
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
                {facts.map((f) => (
                  <MemoryFactRow
                    key={f.id}
                    fact={f}
                    busy={busyId === f.id}
                    editing={editingId === f.id}
                    draft={draft}
                    onDraftChange={setDraft}
                    onEditStart={() => {
                      setEditingId(f.id);
                      setDraft(f.statement);
                    }}
                    onEditCancel={() => setEditingId(null)}
                    onSave={() =>
                      void run(f.id, () => editMemoryFact(f.id, draft.trim()))
                    }
                    onOpenConversation={onOpenConversation}
                    onConfirm={() => void run(f.id, () => confirmMemoryFact(f.id))}
                    onReject={() => {
                      if (window.confirm("确定拒绝这条待确认记忆？")) {
                        void run(f.id, () => rejectMemoryFact(f.id));
                      }
                    }}
                    onForget={() => {
                      if (window.confirm("确定遗忘这条记忆？")) {
                        void run(f.id, () => forgetMemoryFact(f.id));
                      }
                    }}
                  />
                ))}
              </ul>
            ) : null}
            {staleFacts.length > 0 ? (
              <div className="knowledge-card-stale-group">
                <button
                  type="button"
                  className="knowledge-card-stale-toggle"
                  aria-expanded={staleExpanded}
                  onClick={() => setStaleExpanded((v) => !v)}
                >
                  已淡出 · {staleFacts.length}
                </button>
                {staleExpanded ? (
                  <ul className="memory-fact-list knowledge-card-stale-list">
                    {staleFacts.map((f) => (
                      <MemoryFactRow
                        key={f.id}
                        fact={f}
                        busy={busyId === f.id}
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
                          if (window.confirm("确定遗忘这条记忆？")) {
                            void run(f.id, () => forgetMemoryFact(f.id));
                          }
                        }}
                        onRestore={() =>
                          void run(f.id, () => restoreMemoryFact(f.id))
                        }
                      />
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
