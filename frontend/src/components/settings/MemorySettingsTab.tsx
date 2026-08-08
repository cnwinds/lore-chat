import { useCallback, useEffect, useRef, useState } from "react";
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
  ExternalLinkIcon,
  SaveIcon,
  TrashIcon,
  XIcon,
} from "../DocToolbarIcons";

type Props = {
  onOpenConversation?: (conversationId: string) => void;
};

function jumpLabel(conversationIds: string[], canOpen: boolean): string {
  if (conversationIds.length === 0) return "无来源可跳转";
  if (!canOpen) return "无法打开会话";
  if (conversationIds.length > 1) return "选择来源会话";
  return "打开来源会话";
}

function SourceJumpControl({
  conversationIds,
  disabled,
  onOpenConversation,
}: {
  conversationIds: string[];
  disabled?: boolean;
  onOpenConversation?: (conversationId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const canOpen = Boolean(onOpenConversation);
  const hasSources = conversationIds.length > 0;
  const canJump = canOpen && hasSources;
  const multi = conversationIds.length > 1;

  useDismissOnOutsideClick(rootRef, open, () => setOpen(false), {
    escape: true,
    pointerEvent: "mousedown",
  });

  function openOne(cid: string) {
    onOpenConversation?.(cid);
    setOpen(false);
  }

  return (
    <div ref={rootRef} className="doc-overflow-anchor">
      <DocIconBtn
        label={jumpLabel(conversationIds, canOpen)}
        className="memory-fact-icon-btn"
        disabled={disabled || !canJump}
        active={multi ? open : false}
        onClick={() => {
          if (!canJump) return;
          if (!multi) {
            openOne(conversationIds[0]);
            return;
          }
          setOpen((v) => !v);
        }}
        aria-expanded={multi ? open : undefined}
        aria-haspopup={multi ? "menu" : undefined}
      >
        <ExternalLinkIcon />
      </DocIconBtn>
      {open && multi ? (
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

export function MemorySettingsTab({ onOpenConversation }: Props) {
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
        已确认与待确认的长期画像。待确认可晋升或拒绝；已确认可编辑或遗忘。右侧图标可跳转到来源会话。
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
                    <span className="memory-fact-status memory-fact-status--candidate">待确认</span>
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
                    <p className="memory-fact-statement">{f.statement}</p>
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
                    <>
                      <SourceJumpControl
                        conversationIds={conversationIds}
                        disabled={busy}
                        onOpenConversation={onOpenConversation}
                      />
                      {candidate ? (
                        <>
                          <DocIconBtn
                            label="确认"
                            className="memory-fact-icon-btn"
                            disabled={busy}
                            onClick={() => void run(f.id, () => confirmMemoryFact(f.id))}
                          >
                            <CheckIcon />
                          </DocIconBtn>
                          <DocIconBtn
                            label="拒绝"
                            className="memory-fact-icon-btn memory-fact-icon-btn--danger"
                            disabled={busy}
                            onClick={() => {
                              if (window.confirm("确定拒绝这条待确认记忆？")) {
                                void run(f.id, () => rejectMemoryFact(f.id));
                              }
                            }}
                          >
                            <XIcon />
                          </DocIconBtn>
                        </>
                      ) : (
                        <>
                          <DocIconBtn
                            label="编辑"
                            className="memory-fact-icon-btn"
                            disabled={busy}
                            onClick={() => {
                              setEditingId(f.id);
                              setDraft(f.statement);
                            }}
                          >
                            <EditIcon />
                          </DocIconBtn>
                          <DocIconBtn
                            label="遗忘"
                            className="memory-fact-icon-btn memory-fact-icon-btn--danger"
                            disabled={busy}
                            onClick={() => {
                              if (window.confirm("确定遗忘这条记忆？")) {
                                void run(f.id, () => forgetMemoryFact(f.id));
                              }
                            }}
                          >
                            <TrashIcon />
                          </DocIconBtn>
                        </>
                      )}
                    </>
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
