import { useCallback, useEffect, useState } from "react";
import {
  confirmMemoryFact,
  editMemoryFact,
  forgetMemoryFact,
  listMemoryFacts,
  rejectMemoryFact,
  type MemoryFact,
} from "../../api";

type Props = {
  onOpenConversation?: (conversationId: string) => void;
};

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
        已确认与待确认（candidate）的长期画像。可确认晋升、拒绝、编辑或遗忘；点击来源可打开会话。
      </p>
      {error ? <p className="settings-panel-error">{error}</p> : null}
      {facts.length === 0 ? (
        <p className="settings-panel-hint">暂无记忆条目。</p>
      ) : (
        <ul className="memory-fact-list">
          {facts.map((f) => {
            const busy = busyId === f.id;
            const editing = editingId === f.id;
            return (
              <li key={f.id} className="memory-fact-item">
                <div className="memory-fact-meta">
                  <span className={`memory-fact-status memory-fact-status--${f.status || "unknown"}`}>
                    {f.status === "candidate" ? "待确认" : "已确认"}
                  </span>
                  <span className="memory-fact-slot">{f.slot_key}</span>
                  {f.origin ? <span className="memory-fact-origin">{f.origin}</span> : null}
                </div>
                {editing ? (
                  <textarea
                    className="memory-fact-edit"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    rows={3}
                    disabled={busy}
                  />
                ) : (
                  <p className="memory-fact-statement">{f.statement}</p>
                )}
                {f.conversation_ids?.length ? (
                  <div className="memory-fact-sources">
                    来源：
                    {f.conversation_ids.map((cid) => (
                      <button
                        key={cid}
                        type="button"
                        className="memory-fact-source-btn"
                        disabled={!onOpenConversation}
                        onClick={() => onOpenConversation?.(cid)}
                        title={cid}
                      >
                        {cid.slice(0, 8)}…
                      </button>
                    ))}
                  </div>
                ) : null}
                <div className="memory-fact-actions">
                  {editing ? (
                    <>
                      <button
                        type="button"
                        className="settings-btn settings-btn--primary"
                        disabled={busy || !draft.trim()}
                        onClick={() =>
                          void run(f.id, () => editMemoryFact(f.id, draft.trim()))
                        }
                      >
                        保存
                      </button>
                      <button
                        type="button"
                        className="settings-btn"
                        disabled={busy}
                        onClick={() => setEditingId(null)}
                      >
                        取消
                      </button>
                    </>
                  ) : (
                    <>
                      {f.status === "candidate" ? (
                        <>
                          <button
                            type="button"
                            className="settings-btn settings-btn--primary"
                            disabled={busy}
                            onClick={() => void run(f.id, () => confirmMemoryFact(f.id))}
                          >
                            确认
                          </button>
                          <button
                            type="button"
                            className="settings-btn"
                            disabled={busy}
                            onClick={() => void run(f.id, () => rejectMemoryFact(f.id))}
                          >
                            拒绝
                          </button>
                        </>
                      ) : null}
                      <button
                        type="button"
                        className="settings-btn"
                        disabled={busy}
                        onClick={() => {
                          setEditingId(f.id);
                          setDraft(f.statement);
                        }}
                      >
                        编辑
                      </button>
                      <button
                        type="button"
                        className="settings-btn"
                        disabled={busy}
                        onClick={() => {
                          if (window.confirm("确定遗忘这条记忆？")) {
                            void run(f.id, () => forgetMemoryFact(f.id));
                          }
                        }}
                      >
                        遗忘
                      </button>
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
