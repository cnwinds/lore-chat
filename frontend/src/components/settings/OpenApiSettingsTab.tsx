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

function formatWhen(iso?: string | null): string {
  if (!iso) return "尚未调用";
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return iso;
  return new Date(ms).toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function OpenApiSettingsTab() {
  const [personas, setPersonas] = useState<ApiPersona[]>([]);
  const [keys, setKeys] = useState<OpenApiKey[]>([]);
  const [roles, setRoles] = useState<RoleSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [personaName, setPersonaName] = useState("");
  const [personaPrompt, setPersonaPrompt] = useState("");
  const [keyName, setKeyName] = useState("");
  const [keyPersonaId, setKeyPersonaId] = useState("");
  const [newToken, setNewToken] = useState<string | null>(null);
  const [viewing, setViewing] = useState<OpenApiKey | null>(null);
  const [transcript, setTranscript] = useState<
    { title: string; messages: ChatMessage[] }[]
  >([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editPrompt, setEditPrompt] = useState("");
  const [busy, setBusy] = useState(false);
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
      setKeyPersonaId((cur) => {
        if (cur && p.personas.some((item) => item.id === cur)) return cur;
        return p.personas[0]?.id || "";
      });
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

  const handleCreatePersona = async () => {
    const name = personaName.trim();
    if (!name) return;
    setBusy(true);
    try {
      const created = await createApiPersona({
        name,
        system_prompt: personaPrompt,
      });
      setPersonaName("");
      setPersonaPrompt("");
      setKeyPersonaId(created.id);
      showToast("人设已创建");
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "创建人设失败");
    } finally {
      setBusy(false);
    }
  };

  const handleCopyRole = async (roleId: string) => {
    setBusy(true);
    try {
      const created = await createApiPersona({
        name: "从角色复制",
        from_role_id: roleId,
      });
      setKeyPersonaId(created.id);
      showToast("已从角色复制人设（不共用那个角色的沙箱）");
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "复制失败");
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
      showToast("人设已更新，下一轮调用生效");
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  const handleDeletePersona = async (id: string) => {
    if (!window.confirm("删除此人设？仍被密钥使用时会失败。")) return;
    setBusy(true);
    try {
      await deleteApiPersona(id);
      if (editingId === id) setEditingId(null);
      showToast("已删除人设");
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "删除失败");
    } finally {
      setBusy(false);
    }
  };

  const handleCreateKey = async () => {
    const name = keyName.trim();
    if (!name) return;
    setBusy(true);
    try {
      const created = await createOpenApiKey({
        name,
        persona_id: keyPersonaId || undefined,
        persona_name: keyPersonaId ? undefined : name,
      });
      setKeyName("");
      setNewToken(created.token || null);
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
      if (viewing?.id === id) setViewing(null);
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
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载会话失败");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <p className="settings-panel-hint">加载开放接口…</p>;
  }

  return (
    <div className="settings-group open-api-settings">
      <h3 className="settings-group-title">开放接口</h3>
      <p className="settings-group-hint">
        给自己的脚本签发 API Key。人设（名称和提示词）可以多把 Key 共用，改完下一轮都生效。
        每把 Key 会单独建一个隐藏工作角色：自己的沙箱、自己的聊天记录，互不堵塞，也不进左栏。
      </p>
      <p className="settings-group-hint">
        调用 <code>POST /api/v1/chat</code>，请求头{" "}
        <code>Authorization: Bearer lc_live_…</code>
      </p>
      {error ? <p className="settings-panel-error">{error}</p> : null}

      {newToken ? (
        <div className="settings-callout" role="status">
          <p>请立刻复制密钥，关闭后无法再查看完整内容。</p>
          <code className="open-api-token">{newToken}</code>
          <div className="open-api-token-actions">
            <button
              type="button"
              className="settings-btn settings-btn--compact settings-btn--primary"
              onClick={() => {
                void navigator.clipboard.writeText(newToken);
                showToast("已复制");
              }}
            >
              复制
            </button>
            <button
              type="button"
              className="settings-btn settings-btn--compact settings-btn--secondary"
              onClick={() => setNewToken(null)}
            >
              已保存
            </button>
          </div>
        </div>
      ) : null}

      <h4 className="settings-group-title">人设</h4>
      <p className="settings-group-hint">
        只是一套提示词。两把 Key 选同一人设，看起来像同一个角色，底下仍是两个人在干活。
      </p>
      <label className="settings-field">
        <span>名称</span>
        <input
          type="text"
          value={personaName}
          onChange={(e) => setPersonaName(e.target.value)}
          disabled={busy}
          placeholder="例如：周报助手"
        />
      </label>
      <label className="settings-field">
        <span>提示词</span>
        <textarea
          rows={3}
          value={personaPrompt}
          onChange={(e) => setPersonaPrompt(e.target.value)}
          disabled={busy}
          placeholder="这个角色怎么说话、做什么"
        />
      </label>
      <div className="open-api-actions">
        <button
          type="button"
          className="settings-btn settings-btn--compact settings-btn--primary"
          disabled={busy || !personaName.trim()}
          onClick={() => void handleCreatePersona()}
        >
          新建人设
        </button>
      </div>
      {roles.length > 0 ? (
        <label className="settings-field">
          <span>从左栏角色复制（只拷人设，不共用沙箱和聊天）</span>
          <select
            defaultValue=""
            disabled={busy}
            onChange={(e) => {
              const id = e.target.value;
              e.target.value = "";
              if (id) void handleCopyRole(id);
            }}
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
      {personas.length === 0 ? (
        <p className="settings-panel-hint">还没有人设。先建一套，或从左栏角色复制。</p>
      ) : (
        <ul className="open-api-list">
          {personas.map((p) => {
            const used = keyCountByPersona.get(p.id) || 0;
            const editing = editingId === p.id;
            return (
              <li key={p.id} className="open-api-row">
                {editing ? (
                  <div className="open-api-edit">
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
                    <div className="open-api-row-actions">
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
                        className="settings-btn settings-btn--compact settings-btn--secondary"
                        disabled={busy}
                        onClick={() => setEditingId(null)}
                      >
                        取消
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="open-api-row-main">
                      <strong>{p.name}</strong>
                      <span className="settings-panel-hint">
                        {used > 0 ? `被 ${used} 把密钥使用` : "还没有密钥使用"}
                      </span>
                    </div>
                    <div className="open-api-row-actions">
                      <button
                        type="button"
                        className="settings-btn settings-btn--compact settings-btn--secondary"
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
                        className="settings-btn settings-btn--compact settings-btn--secondary"
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
      )}

      <h4 className="settings-group-title">密钥</h4>
      <p className="settings-group-hint">
        每一行是一把独立工作角色。选同一人设也互不堵、聊天记录也分开。同一把 Key 连打两枪，第二枪会先被拒绝。
      </p>
      <label className="settings-field">
        <span>名称</span>
        <input
          type="text"
          value={keyName}
          onChange={(e) => setKeyName(e.target.value)}
          disabled={busy}
          placeholder="例如：周报脚本、给同事甲"
        />
      </label>
      <label className="settings-field">
        <span>使用人设</span>
        <select
          value={keyPersonaId}
          onChange={(e) => setKeyPersonaId(e.target.value)}
          disabled={busy}
        >
          <option value="">创建时用密钥名新建一套</option>
          {personas.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
      <div className="open-api-actions">
        <button
          type="button"
          className="settings-btn settings-btn--compact settings-btn--primary"
          disabled={busy || !keyName.trim()}
          onClick={() => void handleCreateKey()}
        >
          创建密钥
        </button>
      </div>
      {keys.length === 0 ? (
        <p className="settings-panel-hint">还没有密钥。</p>
      ) : (
        <ul className="open-api-list">
          {keys.map((key) => (
            <li key={key.id} className="open-api-row">
              <div className="open-api-row-main">
                <strong>{key.name}</strong>
                <span className="settings-panel-hint">
                  {key.prefix}… · {key.persona?.name || "人设"} · {formatWhen(key.last_used_at)}
                </span>
              </div>
              <div className="open-api-row-actions">
                <button
                  type="button"
                  className="settings-btn settings-btn--compact settings-btn--secondary"
                  disabled={busy}
                  onClick={() => void handleView(key)}
                >
                  查看会话
                </button>
                <button
                  type="button"
                  className="settings-btn settings-btn--compact settings-btn--secondary"
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

      {viewing ? (
        <div className="open-api-transcript">
          <h4 className="settings-group-title">会话 · {viewing.name}</h4>
          <p className="settings-group-hint">只看这一把 Key 的记录，不会混进其他人设或其它 Key。</p>
          {transcript.length === 0 ? (
            <p className="settings-panel-hint">还没有调用记录。</p>
          ) : (
            transcript.map((seg, i) => (
              <section key={`${seg.title}-${i}`}>
                <p>
                  <strong>{seg.title}</strong>
                </p>
                {seg.messages.map((m) => (
                  <p key={m.id || `${seg.title}-${m.role}-${m.ts}`}>
                    <em>{m.role === "user" ? "用户" : "助手"}</em>
                    {": "}
                    {m.text}
                  </p>
                ))}
              </section>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
}
