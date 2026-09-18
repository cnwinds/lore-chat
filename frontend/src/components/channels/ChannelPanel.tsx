import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { listRoles } from "../../api";
import type { RoleSummary } from "../../types/chat";
import {
  createChannelInstance,
  getChannelCredential,
  listChannelInstances,
  listChannelTypes,
  patchChannelInstance,
  revokeChannelInstance,
  type ChannelInstance,
  type ChannelType,
} from "../../api/channelPlugins";
import {
  createApiPersona,
  listApiPersonas,
  updateApiPersona,
  type ApiPersona,
} from "../../api/openApi";
import { copyTextToClipboard } from "../../utils/clipboard";
import type { DocWidth } from "../../types/doc";
import { showToast } from "../../utils/toast";
import {
  EMPTY_CREATE_DRAFT,
  buildCreateKeyRequest,
  buildTypeConfig,
  canSubmitCreateKey,
  channelNextSteps,
  type CreateKeyDraft,
} from "../settings/openApiSettingsModel";
import { ChannelCard } from "./ChannelCard";
import { CreateKeyScreen, PickTypeScreen } from "./ChannelCreateScreens";
import {
  NEW_EXCLUSIVE_VALUE,
  isExclusiveTo,
  personaUsage,
  typeLabel,
  type DetailTab,
} from "./channelUiModel";

type Screen = "home" | "pick-type" | "create";

type Props = {
  docWidth?: DocWidth;
  onClose: () => void;
};

export function ChannelPanel({
  docWidth = "wide",
  onClose,
}: Props) {
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
  const [imHint, setImHint] = useState<string | null>(null);
  const [openTabById, setOpenTabById] = useState<Record<string, DetailTab>>(
    {},
  );
  const [editingPromptId, setEditingPromptId] = useState<string | null>(null);
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

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Escape" || screen === "home") return;
      // 捕获阶段拦住，避免 App 级 Esc 把整层浮窗连同右侧钉住文档一起关掉。
      e.preventDefault();
      e.stopImmediatePropagation();
      setScreen("home");
      setError(null);
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [screen]);

  const usage = useMemo(() => personaUsage(instances), [instances]);

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
    if (!canSubmitCreateKey(draft, createType)) return;
    setBusy(true);
    setError(null);
    try {
      const request = buildCreateKeyRequest(draft);
      const extra = buildTypeConfig(createType, draft);
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
          ...extra,
        });
      } else {
        created = await createChannelInstance({
          type_id: createType,
          ...request,
          ...extra,
        });
      }
      setImHint(channelNextSteps(createType));
      setDraft(EMPTY_CREATE_DRAFT);
      setScreen("home");
      showToast(
        created.token ? "通道已创建，密钥可随时从卡片复制" : "通道已创建",
      );
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "创建通道失败");
    } finally {
      setBusy(false);
    }
  };

  const handleRevoke = async (id: string) => {
    const inst = instances.find((item) => item.id === id);
    const isScript = inst?.type_id === "script_api";
    if (!isScript && inst?.enabled) {
      setError("请先停用通道，再删除");
      return;
    }
    const confirmText = isScript
      ? "吊销后这把 Key 立刻失效，卡片上不再显示可复制密钥。打开开关可重新启用同一把 Key。"
      : "删除后该通道会从列表消失。外部无法再接入；历史仍可查看。";
    if (!window.confirm(confirmText)) return;
    setBusy(true);
    try {
      await revokeChannelInstance(id);
      showToast(isScript ? "已吊销" : "已删除");
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : isScript ? "吊销失败" : "删除失败");
    } finally {
      setBusy(false);
    }
  };

  const handleToggle = async (inst: ChannelInstance) => {
    setBusy(true);
    setError(null);
    try {
      await patchChannelInstance(inst.id, { enabled: !inst.enabled });
      showToast(inst.enabled ? "已停用" : "已启用");
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "更新失败");
    } finally {
      setBusy(false);
    }
  };

  const handleToggleOutput = async (
    inst: ChannelInstance,
    field: "show_thinking" | "show_tool_output",
  ) => {
    const next = !inst[field];
    setInstances((prev) =>
      prev.map((item) => (item.id === inst.id ? { ...item, [field]: next } : item)),
    );
    setError(null);
    try {
      await patchChannelInstance(inst.id, { [field]: next });
    } catch (e: unknown) {
      setInstances((prev) =>
        prev.map((item) =>
          item.id === inst.id ? { ...item, [field]: !!inst[field] } : item,
        ),
      );
      setError(e instanceof Error ? e.message : "更新失败");
    }
  };

  const handleCopy = async (inst: ChannelInstance) => {
    if (inst.type_id === "script_api" && !inst.enabled) {
      showToast("Key 已吊销，无法复制");
      return;
    }
    setBusy(true);
    try {
      const cred = await getChannelCredential(inst.id);
      if (!cred.can_copy_full || !cred.copy_text) {
        showToast("完整密钥未保存在本机。请吊销后重建通道，之后即可随时复制。");
        return;
      }
      const ok = await copyTextToClipboard(cred.copy_text);
      showToast(ok ? "已复制" : "复制失败");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "复制失败");
    } finally {
      setBusy(false);
    }
  };

  const handleSelectPersona = async (inst: ChannelInstance, value: string) => {
    if (!value) return;
    setBusy(true);
    setError(null);
    try {
      if (value === NEW_EXCLUSIVE_VALUE) {
        if (inst.persona_id && isExclusiveTo(inst.persona_id, inst.id, usage)) {
          showToast("已是本通道专属角色");
          return;
        }
        const current = personas.find((p) => p.id === inst.persona_id);
        const created = await createApiPersona({
          name: inst.name,
          system_prompt: current?.system_prompt || "",
        });
        await patchChannelInstance(inst.id, { persona_id: created.id });
        showToast("已改为本通道专属角色");
      } else {
        await patchChannelInstance(inst.id, { persona_id: value });
        showToast("角色已更新");
      }
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "更新角色失败");
    } finally {
      setBusy(false);
    }
  };

  const startEditPrompt = (inst: ChannelInstance) => {
    const persona = personas.find((p) => p.id === inst.persona_id);
    if (!persona) return;
    setEditingPromptId(inst.id);
    setEditName(persona.name);
    setEditPrompt(persona.system_prompt || "");
  };

  const handleSavePrompt = async (inst: ChannelInstance) => {
    if (!inst.persona_id || !editName.trim()) return;
    setBusy(true);
    try {
      await updateApiPersona(inst.persona_id, {
        name: editName.trim(),
        system_prompt: editPrompt,
      });
      setEditingPromptId(null);
      showToast("提示词已更新，下一轮调用生效");
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  const toggleTab = (id: string, tab: DetailTab) => {
    setOpenTabById((prev) => {
      if (prev[id] === tab) {
        const next = { ...prev };
        delete next[id];
        return next;
      }
      return { ...prev, [id]: tab };
    });
  };

  const title =
    screen === "pick-type"
      ? "添加通道"
      : screen === "create"
        ? `添加${typeLabel(createType, types)}`
        : "聊天通道";
  const metaLabel = loading
    ? "加载中…"
    : screen === "home"
      ? `${instances.length} 个通道`
      : null;

  return (
    <div
      className={`kb-float-panel kb-float-panel--${docWidth}`}
      aria-label="聊天通道"
    >
      <header className="kb-float-header">
        <div className="kb-float-header-main">
          <h2 className="kb-float-title">{title}</h2>
        </div>
        <div className="kb-float-header-actions">
          {screen === "home" && instances.length > 0 ? (
            <button
              type="button"
              className="doc-icon-btn"
              disabled={busy}
              onClick={openPicker}
              title="添加通道"
              aria-label="添加通道"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden>
                <path
                  d="M12 5v14M5 12h14"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </svg>
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

      {metaLabel ? <div className="kb-float-meta">{metaLabel}</div> : null}

      <div className="kb-float-body">
        {error ? <div className="kb-float-error">错误：{error}</div> : null}

        {screen === "pick-type" ? (
          <PickTypeScreen
            types={types}
            busy={busy}
            onBack={() => {
              setError(null);
              setScreen("home");
            }}
            onPick={(typeId) => openCreate(typeId)}
          />
        ) : screen === "create" ? (
          <CreateKeyScreen
            draft={draft}
            personas={personas}
            roles={roles}
            busy={busy}
            typeId={createType}
            typeLabel={typeLabel(createType, types)}
            onChange={setDraft}
            onBack={() => {
              setError(null);
              setScreen("pick-type");
            }}
            onSubmit={() => void handleCreate()}
          />
        ) : (
          <div className="channel-panel-home">
            {imHint ? (
              <div className="openapi-token" role="status">
                <p className="openapi-token-warn">{imHint}</p>
                <div className="openapi-token-actions">
                  <button
                    type="button"
                    className="openapi-btn"
                    onClick={() => setImHint(null)}
                  >
                    知道了
                  </button>
                </div>
              </div>
            ) : null}

            {!loading && instances.length === 0 ? (
              <div className="kb-float-empty">
                <div className="kb-float-empty-mark" aria-hidden />
                <p>还没有聊天通道</p>
                <p className="kb-float-empty-hint">
                  添加通道后，脚本或外部 IM 就能把消息送进这个会话。
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
            ) : null}

            {instances.length > 0 ? (
              <ul className="channel-card-list">
                {instances.map((inst) => (
                  <ChannelCard
                    key={inst.id}
                    inst={inst}
                    types={types}
                    personas={personas}
                    usage={usage}
                    busy={busy}
                    activeTab={openTabById[inst.id] ?? null}
                    editingPrompt={editingPromptId === inst.id}
                    editName={editName}
                    editPrompt={editPrompt}
                    onToggle={(item) => void handleToggle(item)}
                    onToggleOutput={(item, field) =>
                      void handleToggleOutput(item, field)
                    }
                    onCopy={(item) => void handleCopy(item)}
                    onToggleTab={toggleTab}
                    onSelectPersona={(item, value) =>
                      void handleSelectPersona(item, value)
                    }
                    onStartEditPrompt={startEditPrompt}
                    onEditName={setEditName}
                    onEditPrompt={setEditPrompt}
                    onSavePrompt={(item) => void handleSavePrompt(item)}
                    onCancelEditPrompt={() => setEditingPromptId(null)}
                    onRevoke={(id) => void handleRevoke(id)}
                  />
                ))}
              </ul>
            ) : null}

          </div>
        )}
      </div>
    </div>
  );
}
