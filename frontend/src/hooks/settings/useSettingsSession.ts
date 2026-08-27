import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type RefObject,
} from "react";
import {
  changePassword,
  clearImageCooldown,
  clearModelCooldown,
  clearSearchCooldown,
  downloadExport,
  getSettings,
  importKb,
  putSettings,
  reindexKb,
  type SettingsAttention,
} from "../../api";
import type { EmbedCandidateDraft, ModelCandidateDraft } from "../../components/settings/providerPresets";
import type { ImageProviderDraft } from "../../components/settings/ImageProviderEditor";
import type { SearchProviderDraft } from "../../components/settings/SearchProviderEditor";
import {
  applyFreeStarterPack,
  starterPackPhase,
  withStarterPackKeys,
  type StarterPackDrafts,
} from "../../components/settings/starterPack";
import { searchProvidersConfigured } from "../../components/settings/settingsAttention";
import { hydrateSettingsDrafts, toSettingsPatch } from "../../components/settings/settingsDrafts";
import type { CooldownStatus } from "../../components/settings/settingsTypes";
import {
  clientAccessOrigin,
  ensurePublicBaseUrlOnLoad,
} from "./ensurePublicBaseUrlOnLoad";
import { runSettingsSaveSideEffects } from "./settingsSavePipeline";
import {
  readStoredSettingsTab,
  writeStoredSettingsTab,
  type SettingsTab,
} from "./settingsTabStorage";
import { useSettingsLiveAttention } from "./useSettingsLiveAttention";

export type { SettingsTab };

type Options = {
  open: boolean;
  navigateToTab?: SettingsTab | null;
  onNavigateToTabHandled?: () => void;
  showLlmSetupGuide?: boolean;
  onLlmConfigured?: () => void;
  attention?: SettingsAttention | null;
  onAttentionChange?: () => void;
  onLiveAttentionChange?: (live: SettingsAttention | null) => void;
  onClose: () => void;
};

export function useSettingsSession({
  open,
  navigateToTab = null,
  onNavigateToTabHandled,
  showLlmSetupGuide = false,
  onLlmConfigured,
  attention = null,
  onAttentionChange,
  onLiveAttentionChange,
  onClose,
}: Options) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [settingsReady, setSettingsReady] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<SettingsTab>(readStoredSettingsTab);

  const [kbPath, setKbPath] = useState("");
  const [publicBaseUrl, setPublicBaseUrl] = useState("");
  const [chatModels, setChatModels] = useState<ModelCandidateDraft[]>([]);
  const [utilityModels, setUtilityModels] = useState<ModelCandidateDraft[]>([]);
  const [embedModels, setEmbedModels] = useState<EmbedCandidateDraft[]>([]);
  const [cooldown, setCooldown] = useState<CooldownStatus>({});
  const [searchProviders, setSearchProviders] = useState<SearchProviderDraft[]>([]);
  const [searchCooldown, setSearchCooldown] = useState<CooldownStatus>({});
  const [imageProviders, setImageProviders] = useState<ImageProviderDraft[]>([]);
  const [imageCooldown, setImageCooldown] = useState<CooldownStatus>({});

  const [minVectorScore, setMinVectorScore] = useState(0.45);
  const [rrfK, setRrfK] = useState(60);
  const [laneCandidateK, setLaneCandidateK] = useState(20);
  const [webSearchDefaultK, setWebSearchDefaultK] = useState(5);

  const [agentMaxToolCalls, setAgentMaxToolCalls] = useState(25);
  const [agentParallelTools, setAgentParallelTools] = useState(true);
  const [agentMaxParallel, setAgentMaxParallel] = useState(4);
  const [sandboxEnabled, setSandboxEnabled] = useState(false);
  const [sandboxTrustMode, setSandboxTrustMode] = useState(true);
  const [sandboxMirrorRegion, setSandboxMirrorRegion] = useState<"cn" | "global">(
    "cn",
  );

  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pwdSaving, setPwdSaving] = useState(false);
  const [pwdMsg, setPwdMsg] = useState<string | null>(null);
  const [pwdError, setPwdError] = useState<string | null>(null);

  const [backupBusy, setBackupBusy] = useState(false);
  const [backupMsg, setBackupMsg] = useState<string | null>(null);
  const [backupError, setBackupError] = useState<string | null>(null);
  const [importMode, setImportMode] = useState<"empty_only" | "overwrite">("empty_only");
  const [importFile, setImportFile] = useState<File | null>(null);
  const importFileRef = useRef<HTMLInputElement>(null);
  const settingsWasOpenRef = useRef(false);
  const searchConfiguredRef = useRef(false);
  const [usageIncomplete, setUsageIncomplete] = useState<number | null>(null);
  const [starterDismissed, setStarterDismissed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSaveMsg(null);
    try {
      const data = await getSettings();
      const drafts = hydrateSettingsDrafts(data, {
        fallbackPublicBaseUrl: clientAccessOrigin(),
      });
      setKbPath(drafts.kbPath);
      setPublicBaseUrl(drafts.publicBaseUrl);
      const urlPersist = await ensurePublicBaseUrlOnLoad(
        drafts.publicBaseUrl,
        drafts.publicBaseUrlFromFallback,
      );
      if (urlPersist.message) setSaveMsg(urlPersist.message);
      setChatModels(drafts.chatModels);
      setUtilityModels(drafts.utilityModels);
      setEmbedModels(drafts.embedModels);
      setCooldown(drafts.modelCooldown);
      setSearchProviders(drafts.searchProviders);
      searchConfiguredRef.current = searchProvidersConfigured(
        drafts.searchProviders,
      );
      setSearchCooldown(drafts.searchCooldown);
      setImageProviders(drafts.imageProviders);
      setImageCooldown(drafts.imageCooldown);
      setMinVectorScore(drafts.minVectorScore);
      setRrfK(drafts.rrfK);
      setLaneCandidateK(drafts.laneCandidateK);
      setWebSearchDefaultK(drafts.webSearchDefaultK);
      setAgentMaxToolCalls(drafts.agentMaxToolCalls);
      setAgentParallelTools(drafts.agentParallelTools);
      setAgentMaxParallel(drafts.agentMaxParallel);
      setSandboxEnabled(drafts.sandboxEnabled);
      setSandboxTrustMode(drafts.sandboxTrustMode);
      setSandboxMirrorRegion(drafts.sandboxMirrorRegion);
      setSettingsReady(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载设置失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      void load();
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPwdMsg(null);
      setPwdError(null);
      setBackupMsg(null);
      setBackupError(null);
      setImportFile(null);
      setImportMode("empty_only");
      setUsageIncomplete(null);
      setStarterDismissed(false);
      if (importFileRef.current) importFileRef.current.value = "";
    }
  }, [open, load]);

  useEffect(() => {
    if (!open) {
      settingsWasOpenRef.current = false;
      return;
    }
    const justOpened = !settingsWasOpenRef.current;
    settingsWasOpenRef.current = true;

    if (navigateToTab) {
      setActiveTab(navigateToTab);
      writeStoredSettingsTab(navigateToTab);
      onNavigateToTabHandled?.();
      return;
    }
    if (!justOpened) return;

    if (showLlmSetupGuide) {
      setActiveTab("model");
    } else {
      setActiveTab(readStoredSettingsTab());
    }
  }, [open, showLlmSetupGuide, navigateToTab, onNavigateToTabHandled]);

  useEffect(() => {
    writeStoredSettingsTab(activeTab);
  }, [activeTab]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const starterDrafts = useMemo(
    () => ({
      chat: chatModels,
      utility: utilityModels,
      embed: embedModels,
      search: searchProviders,
    }),
    [chatModels, utilityModels, embedModels, searchProviders],
  );
  const starterPhase = starterPackPhase(starterDrafts, starterDismissed);

  const liveAttention = useSettingsLiveAttention({
    open,
    loading,
    attention,
    chatModels,
    utilityModels,
    embedModels,
    usageIncomplete,
    onLiveAttentionChange,
  });

  function applyStarterDrafts(next: StarterPackDrafts) {
    setChatModels(next.chat);
    setUtilityModels(next.utility);
    setEmbedModels(next.embed);
    setSearchProviders(next.search);
  }

  async function handleSaveSettings(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSaveMsg(null);
    try {
      const patch = toSettingsPatch({
        publicBaseUrl,
        chatModels,
        utilityModels,
        embedModels,
        searchProviders,
        imageProviders,
        minVectorScore,
        rrfK,
        laneCandidateK,
        webSearchDefaultK,
        agentMaxToolCalls,
        agentParallelTools,
        agentMaxParallel,
        sandboxTrustMode,
        sandboxMirrorRegion,
      });

      const wasSearchConfigured = searchConfiguredRef.current;
      const saved = await putSettings(patch);
      setSaveMsg("已保存并生效");
      runSettingsSaveSideEffects({
        wasSearchConfigured,
        nowSearchConfigured: searchProvidersConfigured(searchProviders),
      });
      await load();
      onAttentionChange?.();
      if (saved.llm_api_key_configured === true) {
        onLlmConfigured?.();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleChangePassword(e: FormEvent) {
    e.preventDefault();
    setPwdError(null);
    setPwdMsg(null);

    if (newPassword.length < 8) {
      setPwdError("新密码至少需要 8 位");
      return;
    }
    if (newPassword !== confirmPassword) {
      setPwdError("两次输入的新密码不一致");
      return;
    }

    setPwdSaving(true);
    try {
      await changePassword(oldPassword, newPassword);
      setPwdMsg("密码已更新");
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setPwdError(err instanceof Error ? err.message : "修改密码失败");
    } finally {
      setPwdSaving(false);
    }
  }

  async function handleExport() {
    setBackupBusy(true);
    setBackupError(null);
    setBackupMsg(null);
    try {
      await downloadExport();
      setBackupMsg("知识库已导出");
    } catch (err) {
      setBackupError(err instanceof Error ? err.message : "导出失败");
    } finally {
      setBackupBusy(false);
    }
  }

  async function handleImport() {
    if (!importFile) {
      setBackupError("请选择要导入的 zip 文件");
      return;
    }
    if (importMode === "overwrite") {
      const ok = window.confirm(
        "将先自动备份现有知识库，再覆盖。确定？",
      );
      if (!ok) return;
    }

    setBackupBusy(true);
    setBackupError(null);
    setBackupMsg(null);
    try {
      const result = await importKb(importFile, importMode);
      const msg =
        result.backup_path != null
          ? `${result.message}（备份：${result.backup_path}）`
          : result.message;
      setBackupMsg(msg);
      setImportFile(null);
      await load();
    } catch (err) {
      setBackupError(err instanceof Error ? err.message : "导入失败");
    } finally {
      setBackupBusy(false);
    }
  }

  async function handleReindex() {
    setBackupBusy(true);
    setBackupError(null);
    setBackupMsg(null);
    try {
      const result = await reindexKb();
      setBackupMsg(
        `索引已重建：文档 ${result.docs_indexed}，会话 FTS ${result.conversations_fts}，会话向量 ${result.conversations_vector}`,
      );
    } catch (err) {
      setBackupError(err instanceof Error ? err.message : "重建索引失败");
    } finally {
      setBackupBusy(false);
    }
  }

  async function clearModelCooldownFor(candidateId: string) {
    try {
      const res = await clearModelCooldown({ candidate_id: candidateId });
      if (res.model_cooldown && typeof res.model_cooldown === "object") {
        setCooldown(res.model_cooldown as CooldownStatus);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "清除冷却失败");
    }
  }

  async function clearSearchCooldownFor(candidateId: string) {
    try {
      const res = await clearSearchCooldown({ provider_id: candidateId });
      if (res.search_cooldown && typeof res.search_cooldown === "object") {
        setSearchCooldown(res.search_cooldown as CooldownStatus);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "清除冷却失败");
    }
  }

  async function clearImageCooldownFor(candidateId: string) {
    try {
      const res = await clearImageCooldown({ provider_id: candidateId });
      if (res.image_cooldown && typeof res.image_cooldown === "object") {
        setImageCooldown(res.image_cooldown as CooldownStatus);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "清除冷却失败");
    }
  }

  return {
    loading,
    saving,
    settingsReady,
    saveMsg,
    error,
    activeTab,
    setActiveTab,
    kbPath,
    publicBaseUrl,
    setPublicBaseUrl,
    chatModels,
    setChatModels,
    utilityModels,
    setUtilityModels,
    embedModels,
    setEmbedModels,
    cooldown,
    searchProviders,
    setSearchProviders,
    searchCooldown,
    imageProviders,
    setImageProviders,
    imageCooldown,
    minVectorScore,
    setMinVectorScore,
    rrfK,
    setRrfK,
    laneCandidateK,
    setLaneCandidateK,
    webSearchDefaultK,
    setWebSearchDefaultK,
    agentMaxToolCalls,
    setAgentMaxToolCalls,
    agentParallelTools,
    setAgentParallelTools,
    agentMaxParallel,
    setAgentMaxParallel,
    sandboxEnabled,
    sandboxTrustMode,
    setSandboxTrustMode,
    sandboxMirrorRegion,
    setSandboxMirrorRegion,
    oldPassword,
    setOldPassword,
    newPassword,
    setNewPassword,
    confirmPassword,
    setConfirmPassword,
    pwdSaving,
    pwdMsg,
    pwdError,
    backupBusy,
    backupMsg,
    backupError,
    importMode,
    setImportMode,
    importFile,
    setImportFile,
    importFileRef: importFileRef as RefObject<HTMLInputElement | null>,
    usageIncomplete,
    setUsageIncomplete,
    starterDismissed,
    setStarterDismissed,
    starterDrafts,
    starterPhase,
    liveAttention,
    applyStarterDrafts,
    handleSaveSettings,
    handleChangePassword,
    handleExport,
    handleImport,
    handleReindex,
    clearModelCooldownFor,
    clearSearchCooldownFor,
    clearImageCooldownFor,
  };
}
