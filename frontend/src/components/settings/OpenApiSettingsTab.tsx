import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { listRoles } from "../../api";
import type { ChatMessage, RoleSummary } from "../../types/chat";
import {
  createChannelInstance,
  getChannelTimeline,
  listChannelInstances,
  listChannelTypes,
  revokeChannelInstance,
  type ChannelInstance,
  type ChannelType,
} from "../../api/channelPlugins";
import {
  createApiPersona,
  deleteApiPersona,
  listApiPersonas,
  updateApiPersona,
  type ApiPersona,
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

type Screen = "home" | "pick-type" | "create" | "logs";

type TranscriptSeg = { title: string; messages: ChatMessage[] };

const TYPE_MARK: Record<string, string> = {
  script_api: "脚",
  feishu: "飞",
  slack: "S",
  wecom: "企",
  dingtalk: "钉",
};

function typeLabel(typeId: string, types: ChannelType[]): string {
  return types.find((item) => item.type_id === typeId)?.display_name || typeId;
}

function statusLabel(inst: ChannelInstance): { text: string; kind: string } {
  if (inst.status === "error") {
    return { text: inst.status_detail || "校验失败", kind: "error" };
  }
  if (inst.enabled) return { text: "已启用", kind: "enabled" };
  return { text: "未启用", kind: "disabled" };
}

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
  const [instances, setInstances] = useState<ChannelInstance[]>([]);
  const [types, setTypes] = useState<ChannelType[]>([]);
  const [roles, setRoles] = useState<RoleSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [screen, setScreen] = useState<Screen>("home");
  const [draft, setDraft] = useState<CreateKeyDraft>(EMPTY_CREATE_DRAFT);
  const [createType, setCreateType] = useState("script_api");
  const [newToken, setNewToken] = useState<string | null>(null);
  const [viewing, setViewing] = useState<ChannelInstance | null>(null);
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
      const [p, inst, t, r] = await Promise.all([
        listApiPersonas(),
        listChannelInstances(),
        listChannelTypes().catch(() => ({ types: [] as ChannelType[] })),
        listRoles(),
      ]);
      if (!mountedRef.current) return;
      setPersonas(p.personas);
      setInstances(inst.instances);
      setTypes(t.types);
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

  const channelCountByPersona = useMemo(() => {
    const counts = new Map<string, number>();
    for (const inst of instances) {
      if (!inst.enabled) continue;
      const pid = inst.persona_id || "";
      if (!pid) continue;
      counts.set(pid, (counts.get(pid) || 0) + 1);
    }
    return counts;
  }, [instances]);

  const openPicker = () => {
    setError(null);
    setScreen("pick-type");
  };

  const openCreate = (typeId: string) => {
    setError(null);
    setCreateType(typeId);
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
      const request = buildCreateKeyRequest(draft);
      let created;
      if (draft.voice === "copy") {
        const copied = await createApiPersona({
          name: "从角色复制",
          from_role_id: draft.copyRoleId,
        });
        created = await createChannelInstance({
          type_id: createType,
          name: draft.name.trim(),
          persona_id: copied.id,
        });
      } else {
        created = await createChannelInstance({
          type_id: createType,
          ...request,
        });
      }
      setNewToken(created.token || null);
      setDraft(EMPTY_CREATE_DRAFT);
      setScreen("home");
      showToast(created.token ? "通道已创建，请立刻复制密钥" : "通道已创建");
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "创建通道失败");
    } finally {
      setBusy(false);
    }
  };

  const handleRevoke = async (id: string) => {
    if (!window.confirm("停用后脚本将无法再调用。历史仍可查看。")) return;
    setBusy(true);
    try {
      await revokeChannelInstance(id);
      showToast("已停用");
      if (viewing?.id === id) {
        setViewing(null);
        setScreen("home");
      }
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "停用失败");
    } finally {
      setBusy(false);
    }
  };

  const handleView = async (inst: ChannelInstance) => {
    if (!inst.role_id) return;
    setBusy(true);
    setError(null);
    try {
      const tl = await getChannelTimeline(inst.role_id);
      setViewing(inst);
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
    if (!window.confirm("删除这套说话方式？仍被通道使用时会失败。")) return;
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

  if (screen === "pick-type") {
    return (
      <PickTypeScreen
        types={types}
        busy={busy}
        error={error}
        onBack={() => {
          setError(null);
          setScreen("home");
        }}
        onPick={(typeId) => openCreate(typeId)}
      />
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
        typeLabel={typeLabel(createType, types)}
        onChange={setDraft}
        onBack={() => {
          setError(null);
          setScreen("pick-type");
        }}
        onSubmit={() => void handleCreate()}
      />
    );
  }

  if (screen === "logs" && viewing) {
    return (
      <LogsScreen
        instance={viewing}
        transcript={transcript}
        error={error}
        onBack={() => {
          setViewing(null);
          setTranscript([]);
          setError(null);
          setScreen("home");
        }}
      />
    );
  }

  return (
    <div className="openapi">
      <header className="openapi-header">
        <div>
          <h3 className="openapi-title">聊天通道</h3>
          <p className="openapi-lead">
            脚本、微信、飞书、Slack 等，都是聊天通道。
          </p>
        </div>
        {instances.length > 0 ? (
          <button
            type="button"
            className="settings-btn settings-btn--compact settings-btn--primary"
            disabled={busy}
            onClick={openPicker}
          >
            添加通道
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

      {instances.length === 0 ? (
        <div className="openapi-empty">
          <span className="openapi-empty-icon" aria-hidden />
          <p className="openapi-empty-title">还没有聊天通道</p>
          <p className="openapi-empty-hint">
            添加后，脚本或外部聊天就能接到这里。
          </p>
          <button
            type="button"
            className="settings-btn settings-btn--compact settings-btn--primary"
            disabled={busy}
            onClick={openPicker}
          >
            添加通道
          </button>
        </div>
      ) : (
        <ul className="openapi-list">
          {instances.map((inst) => {
            const status = statusLabel(inst);
            const prefix = inst.config?.key_prefix;
            return (
              <li key={inst.id} className="openapi-card">
                <div className="openapi-card-top">
                  <div className="openapi-card-identity">
                    <span
                      className={`openapi-type-icon openapi-type-icon--${inst.type_id}`}
                      aria-hidden
                    >
                      {TYPE_MARK[inst.type_id] || "·"}
                    </span>
                    <h4 className="openapi-card-title">{inst.name}</h4>
                  </div>
                  <span className={`openapi-status openapi-status--${status.kind}`}>
                    {status.text}
                  </span>
                </div>
                <div className="openapi-card-badges">
                  <span className="openapi-voice">
                    {inst.persona?.name || "默认"}
                  </span>
                  <span className="openapi-type-name">
                    {typeLabel(inst.type_id, types)}
                  </span>
                </div>
                <p className="openapi-card-meta">
                  {prefix ? `${prefix}… · ` : ""}
                  {formatOpenApiWhen(inst.last_event_at)}
                </p>
                <div className="openapi-card-actions">
                  <button
                    type="button"
                    className="openapi-btn"
                    disabled={busy}
                    onClick={() => void handleView(inst)}
                  >
                    查看会话
                  </button>
                  {inst.enabled ? (
                    <button
                      type="button"
                      className="openapi-btn openapi-btn--danger"
                      disabled={busy}
                      onClick={() => void handleRevoke(inst.id)}
                    >
                      吊销
                    </button>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {instances.some((item) => item.type_id === "script_api" && item.enabled) ? (
        <details className="openapi-more">
          <summary>接入说明 · 脚本 / HTTP</summary>
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
            多个通道可以共用一套提示词。改完下一轮都生效。
          </p>
          <ul className="openapi-persona-list">
            {personas.map((p) => {
              const used = channelCountByPersona.get(p.id) || 0;
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
                          {used > 0 ? `${used} 个通道在用` : "未被使用"}
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

function PickTypeScreen({
  types,
  busy,
  error,
  onBack,
  onPick,
}: {
  types: ChannelType[];
  busy: boolean;
  error: string | null;
  onBack: () => void;
  onPick: (typeId: string) => void;
}) {
  const cards =
    types.length > 0
      ? types
      : [
          {
            type_id: "script_api",
            display_name: "脚本 / HTTP",
            available: true,
            ingress: "http_bearer",
            needs_public_url: false,
          },
        ];
  return (
    <div className="openapi">
      <button type="button" className="openapi-back" onClick={onBack}>
        ← 返回
      </button>
      <header className="openapi-header">
        <div>
          <h3 className="openapi-title">添加通道</h3>
          <p className="openapi-lead">先选类型。未实现的会标明即将支持。</p>
        </div>
      </header>
      {error ? <p className="settings-panel-error">{error}</p> : null}
      <ul className="openapi-type-grid">
        {cards.map((item) => (
          <li key={item.type_id}>
            <button
              type="button"
              className={`openapi-type-card${item.available ? "" : " openapi-type-card--soon"}`}
              disabled={busy || !item.available}
              onClick={() => onPick(item.type_id)}
            >
              <span
                className={`openapi-type-icon openapi-type-icon--${item.type_id}`}
                aria-hidden
              >
                {TYPE_MARK[item.type_id] || "·"}
              </span>
              <strong>{item.display_name}</strong>
              <span>{item.available ? "现在可用" : "即将支持"}</span>
            </button>
          </li>
        ))}
      </ul>
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
  typeLabel: selectedType,
  onChange,
  onBack,
  onSubmit,
}: {
  draft: CreateKeyDraft;
  personas: ApiPersona[];
  roles: RoleSummary[];
  busy: boolean;
  error: string | null;
  typeLabel: string;
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
          <h3 className="openapi-title">添加{selectedType}</h3>
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
            <option value="default">默认（和通道同名）</option>
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
            {busy ? "创建中…" : "创建并启用"}
          </button>
        </footer>
      </form>
    </div>
  );
}

function LogsScreen({
  instance,
  transcript,
  error,
  onBack,
}: {
  instance: ChannelInstance;
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
          <h3 className="openapi-title">{instance.name}</h3>
          <p className="openapi-lead">只看这一路通道的聊天记录。</p>
        </div>
      </header>
      {error ? <p className="settings-panel-error">{error}</p> : null}
      {transcript.length === 0 ? (
        <div className="openapi-empty">
          <p className="openapi-empty-title">还没有调用</p>
          <p className="openapi-empty-hint">消息进来之后，记录会出现在这里。</p>
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
