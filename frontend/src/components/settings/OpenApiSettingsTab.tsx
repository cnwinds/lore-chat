import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { listRoles } from "../../api";
import type { ChatMessage, RoleSummary } from "../../types/chat";
import {
  createApiPersona,
  createOpenApiKey,
  deleteApiPersona,
  getOpenApiKeyTimeline,
  listApiPersonas,
  listOpenApiKeys,
  revokeOpenApiKey,
  updateApiPersona,
  type ApiPersona,
  type OpenApiKey,
} from "../../api/openApi";
import { showToast } from "../../utils/toast";
import {
  EMPTY_CREATE_DRAFT,
  buildCreateKeyRequest,
  canSubmitCreateKey,
  chatCurlExample,
  formatOpenApiWhen,
  type CreateKeyDraft,
  type VoiceMode,
} from "./openApiSettingsModel";

type Screen = "keys" | "create" | "logs";

type TranscriptSeg = { title: string; messages: ChatMessage[] };

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export function OpenApiSettingsTab() {
  const [personas, setPersonas] = useState<ApiPersona[]>([]);
  const [keys, setKeys] = useState<OpenApiKey[]>([]);
  const [roles, setRoles] = useState<RoleSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [screen, setScreen] = useState<Screen>("keys");
  const [draft, setDraft] = useState<CreateKeyDraft>(EMPTY_CREATE_DRAFT);
  const [newToken, setNewToken] = useState<string | null>(null);
  const [viewing, setViewing] = useState<OpenApiKey | null>(null);
  const [transcript, setTranscript] = useState<TranscriptSeg[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editPrompt, setEditPrompt] = useState("");
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [p, k, r] = await Promise.all([
        listApiPersonas(),
        listOpenApiKeys(),
        listRoles(),
      ]);
      if (!mountedRef.current) return;
      setPersonas(p.personas);
      setKeys(k.keys.filter((item) => !item.revoked));
      setRoles(r.roles);
    } catch (e: unknown) {
      if (!mountedRef.current) return;
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const keyCountByPersona = useMemo(() => {
    const counts = new Map<string, number>();
    for (const key of keys) {
      const pid = key.persona_id || "";
      if (!pid) continue;
      counts.set(pid, (counts.get(pid) || 0) + 1);
    }
    return counts;
  }, [keys]);

  const openCreate = () => {
    setError(null);
    setDraft({
      ...EMPTY_CREATE_DRAFT,
      personaId: personas[0]?.id || "",
    });
    setScreen("create");
  };

  const handleCreate = async () => {
    if (!canSubmitCreateKey(draft)) return;
    setBusy(true);
    setError(null);
    try {
      let created;
      if (draft.voice === "copy") {
        const copied = await createApiPersona({
          name: "从角色复制",
          from_role_id: draft.copyRoleId,
        });
        created = await createOpenApiKey({
          name: draft.name.trim(),
          persona_id: copied.id,
        });
      } else {
        created = await createOpenApiKey(buildCreateKeyRequest(draft));
      }
      setNewToken(created.token || null);
      setDraft(EMPTY_CREATE_DRAFT);
      setScreen("keys");
      showToast("密钥已创建，请立刻复制");
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "创建密钥失败");
    } finally {
      setBusy(false);
    }
  };

  const handleRevoke = async (id: string) => {
    if (!window.confirm("吊销后脚本将无法再调用。历史仍可查看。")) return;
    setBusy(true);
    try {
      await revokeOpenApiKey(id);
      showToast("已吊销");
      if (viewing?.id === id) {
        setViewing(null);
        setScreen("keys");
      }
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "吊销失败");
    } finally {
      setBusy(false);
    }
  };

  const handleView = async (key: OpenApiKey) => {
    if (!key.role_id) return;
    setBusy(true);
    setError(null);
    try {
      const tl = await getOpenApiKeyTimeline(key.role_id);
      setViewing(key);
      setTranscript(
        (tl.segments || []).map((seg) => ({
          title: seg.title || "会话",
          messages: (seg.messages || []) as ChatMessage[],
        })),
      );
      setScreen("logs");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载会话失败");
    } finally {
      setBusy(false);
    }
  };

  const handleSavePersona = async (id: string) => {
    const name = editName.trim();
    if (!name) return;
    setBusy(true);
    try {
      await updateApiPersona(id, {
        name,
        system_prompt: editPrompt,
      });
      setEditingId(null);
      showToast("提示词已更新，下一轮调用生效");
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  const handleDeletePersona = async (id: string) => {
    if (!window.confirm("删除这套说话方式？仍被密钥使用时会失败。")) return;
    setBusy(true);
    try {
      await deleteApiPersona(id);
      if (editingId === id) setEditingId(null);
      showToast("已删除");
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "删除失败");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="openapi openapi--loading">
        <div className="openapi-skeleton" />
        <div className="openapi-skeleton openapi-skeleton--short" />
      </div>
    );
  }

  if (screen === "create") {
    return (
      <CreateKeyScreen
        draft={draft}
        personas={personas}
        roles={roles}
        busy={busy}
        error={error}
        onChange={setDraft}
        onBack={() => {
          setError(null);
          setScreen("keys");
        }}
        onSubmit={() => void handleCreate()}
      />
    );
  }

  if (screen === "logs" && viewing) {
    return (
      <LogsScreen
        keyItem={viewing}
        transcript={transcript}
        error={error}
        onBack={() => {
          setViewing(null);
          setTranscript([]);
          setError(null);
          setScreen("keys");
        }}
      />
    );
  }

  return (
    <div className="openapi">
      <header className="openapi-header">
        <div>
          <h3 className="openapi-title">开放接口</h3>
          <p className="openapi-lead">
            给脚本签发密钥。每把密钥独立会话和沙箱。
          </p>
        </div>
        {keys.length > 0 ? (
          <button
            type="button"
            className="settings-btn settings-btn--compact settings-btn--primary"
            disabled={busy}
            onClick={openCreate}
          >
            创建密钥
          </button>
        ) : null}
      </header>

      {error ? <p className="settings-panel-error">{error}</p> : null}

      {newToken ? (
        <TokenBanner
          token={newToken}
          onDismiss={() => setNewToken(null)}
        />
      ) : null}

      {keys.length === 0 ? (
        <div className="openapi-empty">
          <span className="openapi-empty-icon" aria-hidden />
          <p className="openapi-empty-title">还没有密钥</p>
          <p className="openapi-empty-hint">
            创建一把，就能用脚本调用 Lore Chat。
          </p>
          <button
            type="button"
            className="settings-btn settings-btn--compact settings-btn--primary"
            disabled={busy}
            onClick={openCreate}
          >
            创建密钥
          </button>
        </div>
      ) : (
        <ul className="openapi-list">
          {keys.map((key) => (
            <li key={key.id} className="openapi-card">
              <div className="openapi-card-top">
                <h4 className="openapi-card-title">{key.name}</h4>
                <span className="openapi-voice">
                  {key.persona?.name || "默认"}
                </span>
              </div>
              <p className="openapi-card-meta">
                {key.prefix}… · {formatOpenApiWhen(key.last_used_at)}
              </p>
              <div className="openapi-card-actions">
                <button
                  type="button"
                  className="openapi-btn"
                  disabled={busy}
                  onClick={() => void handleView(key)}
                >
                  查看会话
                </button>
                <button
                  type="button"
                  className="openapi-btn openapi-btn--danger"
                  disabled={busy}
                  onClick={() => void handleRevoke(key.id)}
                >
                  吊销
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {keys.length > 0 ? (
        <details className="openapi-more">
          <summary>调用方式</summary>
          <p className="openapi-more-hint">
            <code>POST /api/v1/chat</code>
            ，请求头 <code>Authorization: Bearer lc_live_…</code>
          </p>
          <pre className="openapi-curl">{chatCurlExample()}</pre>
        </details>
      ) : null}

      {personas.length > 0 ? (
        <details className="openapi-more">
          <summary>说话方式 · {personas.length}</summary>
          <p className="openapi-more-hint">
            多把密钥可以共用一套提示词。改完下一轮都生效。
          </p>
          <ul className="openapi-persona-list">
            {personas.map((p) => {
              const used = keyCountByPersona.get(p.id) || 0;
              const editing = editingId === p.id;
              return (
                <li key={p.id} className="openapi-persona">
                  {editing ? (
                    <div className="openapi-persona-edit">
                      <label className="settings-field">
                        <span>名称</span>
                        <input
                          type="text"
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          disabled={busy}
                        />
                      </label>
                      <label className="settings-field">
                        <span>提示词</span>
                        <textarea
                          rows={3}
                          value={editPrompt}
                          onChange={(e) => setEditPrompt(e.target.value)}
                          disabled={busy}
                        />
                      </label>
                      <div className="openapi-card-actions">
                        <button
                          type="button"
                          className="settings-btn settings-btn--compact settings-btn--primary"
                          disabled={busy || !editName.trim()}
                          onClick={() => void handleSavePersona(p.id)}
                        >
                          保存
                        </button>
                        <button
                          type="button"
                          className="openapi-btn"
                          disabled={busy}
                          onClick={() => setEditingId(null)}
                        >
                          取消
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="openapi-persona-main">
                        <strong>{p.name}</strong>
                        <span>
                          {used > 0 ? `${used} 把密钥在用` : "未被使用"}
                        </span>
                      </div>
                      <div className="openapi-card-actions">
                        <button
                          type="button"
                          className="openapi-btn"
                          disabled={busy}
                          onClick={() => {
                            setEditingId(p.id);
                            setEditName(p.name);
                            setEditPrompt(p.system_prompt || "");
                          }}
                        >
                          编辑
                        </button>
                        <button
                          type="button"
                          className="openapi-btn openapi-btn--danger"
                          disabled={busy}
                          onClick={() => void handleDeletePersona(p.id)}
                        >
                          删除
                        </button>
                      </div>
                    </>
                  )}
                </li>
              );
            })}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

function TokenBanner({
  token,
  onDismiss,
}: {
  token: string;
  onDismiss: () => void;
}) {
  return (
    <div className="openapi-token" role="status">
      <p className="openapi-token-warn">只显示这一次，请立刻复制保存。</p>
      <code className="openapi-token-value">{token}</code>
      <div className="openapi-token-actions">
        <button
          type="button"
          className="settings-btn settings-btn--compact settings-btn--primary"
          onClick={() => {
            void copyText(token).then((ok) => {
              showToast(ok ? "已复制密钥" : "复制失败");
            });
          }}
        >
          复制密钥
        </button>
        <button
          type="button"
          className="openapi-btn"
          onClick={() => {
            void copyText(chatCurlExample(token)).then((ok) => {
              showToast(ok ? "已复制调用示例" : "复制失败");
            });
          }}
        >
          复制 curl
        </button>
        <button type="button" className="openapi-btn" onClick={onDismiss}>
          已保存
        </button>
      </div>
    </div>
  );
}

function CreateKeyScreen({
  draft,
  personas,
  roles,
  busy,
  error,
  onChange,
  onBack,
  onSubmit,
}: {
  draft: CreateKeyDraft;
  personas: ApiPersona[];
  roles: RoleSummary[];
  busy: boolean;
  error: string | null;
  onChange: (next: CreateKeyDraft) => void;
  onBack: () => void;
  onSubmit: () => void;
}) {
  const voiceValue =
    draft.voice === "existing" && draft.personaId
      ? `persona:${draft.personaId}`
      : draft.voice;

  const setVoice = (value: string) => {
    if (value.startsWith("persona:")) {
      onChange({
        ...draft,
        voice: "existing",
        personaId: value.slice("persona:".length),
      });
      return;
    }
    onChange({ ...draft, voice: value as VoiceMode });
  };

  return (
    <div className="openapi">
      <button type="button" className="openapi-back" onClick={onBack}>
        ← 返回
      </button>
      <header className="openapi-header">
        <div>
          <h3 className="openapi-title">创建密钥</h3>
          <p className="openapi-lead">填个名字就行。说话方式可先不改。</p>
        </div>
      </header>
      {error ? <p className="settings-panel-error">{error}</p> : null}
      <form
        className="openapi-form"
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
      >
        <label className="settings-field">
          <span>名称</span>
          <input
            type="text"
            value={draft.name}
            onChange={(e) => onChange({ ...draft, name: e.target.value })}
            disabled={busy}
            placeholder="例如：周报脚本"
            autoFocus
          />
        </label>
        <label className="settings-field">
          <span>说话方式</span>
          <select
            value={voiceValue}
            onChange={(e) => setVoice(e.target.value)}
            disabled={busy}
          >
            <option value="default">默认（和密钥同名）</option>
            {personas.map((p) => (
              <option key={p.id} value={`persona:${p.id}`}>
                {p.name}
              </option>
            ))}
            <option value="new">新建一套…</option>
            {roles.length > 0 ? (
              <option value="copy">从左栏角色复制…</option>
            ) : null}
          </select>
        </label>
        {draft.voice === "new" ? (
          <>
            <label className="settings-field">
              <span>人设名称</span>
              <input
                type="text"
                value={draft.personaName}
                onChange={(e) =>
                  onChange({ ...draft, personaName: e.target.value })
                }
                disabled={busy}
                placeholder="例如：周报助手"
              />
            </label>
            <label className="settings-field">
              <span>提示词</span>
              <textarea
                rows={3}
                value={draft.personaPrompt}
                onChange={(e) =>
                  onChange({ ...draft, personaPrompt: e.target.value })
                }
                disabled={busy}
                placeholder="怎么说话、做什么（可选）"
              />
            </label>
          </>
        ) : null}
        {draft.voice === "copy" ? (
          <label className="settings-field">
            <span>从哪个角色复制</span>
            <select
              value={draft.copyRoleId}
              onChange={(e) =>
                onChange({ ...draft, copyRoleId: e.target.value })
              }
              disabled={busy}
            >
              <option value="">选择角色…</option>
              {roles.map((role) => (
                <option key={role.id} value={role.id}>
                  {role.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <footer className="openapi-form-footer">
          <button
            type="button"
            className="openapi-btn"
            disabled={busy}
            onClick={onBack}
          >
            取消
          </button>
          <button
            type="submit"
            className="settings-btn settings-btn--compact settings-btn--primary"
            disabled={busy || !canSubmitCreateKey(draft)}
          >
            {busy ? "创建中…" : "创建"}
          </button>
        </footer>
      </form>
    </div>
  );
}

function LogsScreen({
  keyItem,
  transcript,
  error,
  onBack,
}: {
  keyItem: OpenApiKey;
  transcript: TranscriptSeg[];
  error: string | null;
  onBack: () => void;
}) {
  return (
    <div className="openapi">
      <button type="button" className="openapi-back" onClick={onBack}>
        ← 返回
      </button>
      <header className="openapi-header">
        <div>
          <h3 className="openapi-title">{keyItem.name}</h3>
          <p className="openapi-lead">只看这一把密钥的调用记录。</p>
        </div>
      </header>
      {error ? <p className="settings-panel-error">{error}</p> : null}
      {transcript.length === 0 ? (
        <div className="openapi-empty">
          <p className="openapi-empty-title">还没有调用</p>
          <p className="openapi-empty-hint">脚本调过之后，记录会出现在这里。</p>
        </div>
      ) : (
        <div className="openapi-logs">
          {transcript.map((seg, i) => (
            <section key={`${seg.title}-${i}`} className="openapi-log-seg">
              <h4>{seg.title}</h4>
              {seg.messages.map((m) => (
                <article
                  key={m.id || `${seg.title}-${m.role}-${m.ts}`}
                  className={`openapi-msg openapi-msg--${m.role}`}
                >
                  <span>{m.role === "user" ? "调用" : "回复"}</span>
                  <p>{m.text?.trim() || "（无正文）"}</p>
                </article>
              ))}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
