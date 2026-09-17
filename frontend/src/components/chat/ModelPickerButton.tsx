import { useCallback, useEffect, useRef, useState } from "react";
import { getSettings, putSettings } from "../../api";
import { FixedOverflowMenu } from "../FixedOverflowMenu";
import { showToast } from "../../utils/toast";

type ChatModelEntry = { id?: string; model?: string };

type Props = {
  disabled?: boolean;
};

function modelName(entry: ChatModelEntry): string {
  const m = (entry.model || "").trim();
  return m || (entry.id || "").trim() || "未命名模型";
}

/**
 * 对话模型选择：列出设置里的对话模型链（顺序即优先级），
 * 选中即把该模型移到链首并保存——下一次回合起生效。
 */
export function ModelPickerButton({ disabled = false }: Props) {
  const [open, setOpen] = useState(false);
  const [models, setModels] = useState<ChatModelEntry[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [savingIndex, setSavingIndex] = useState<number | null>(null);
  const anchorRef = useRef<HTMLButtonElement>(null);

  const loadModels = useCallback(async () => {
    setLoading(true);
    try {
      const s = await getSettings();
      const raw = s.chat_models;
      setModels(Array.isArray(raw) ? (raw as ChatModelEntry[]) : []);
    } catch {
      setModels([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadModels();
  }, [loadModels]);

  useEffect(() => {
    if (open) void loadModels();
  }, [open, loadModels]);

  const pick = async (index: number) => {
    if (!models || savingIndex != null) return;
    if (index === 0) {
      setOpen(false);
      return;
    }
    const next = [models[index], ...models.filter((_, i) => i !== index)];
    setSavingIndex(index);
    try {
      await putSettings({ chat_models: next });
      setModels(next);
      showToast(`对话模型已切换：${modelName(next[0])}`);
      setOpen(false);
    } catch {
      showToast("切换失败，请重试");
    } finally {
      setSavingIndex(null);
    }
  };

  const currentName = models?.[0] ? modelName(models[0]) : null;

  return (
    <>
      <button
        ref={anchorRef}
        type="button"
        className="composer-model-btn"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        title="选择对话模型（选中后移到优先级首位）"
        aria-label="选择对话模型"
        aria-expanded={open}
      >
        <span className="composer-model-btn-name">{currentName ?? "模型"}</span>
        <svg width="9" height="9" viewBox="0 0 10 10" fill="none" aria-hidden>
          <path
            d="M1.5 3.2 5 6.8l3.5-3.6"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      <FixedOverflowMenu
        open={open}
        anchorRef={anchorRef}
        align="start"
        label="对话模型"
        className="composer-model-menu"
        onDismiss={() => setOpen(false)}
      >
        {loading && models == null ? (
          <p className="composer-model-menu-hint">加载中…</p>
        ) : !models || models.length === 0 ? (
          <p className="composer-model-menu-hint">
            还没有配置对话模型，请到 设置 → 模型 添加。
          </p>
        ) : (
          models.map((m, i) => (
            <button
              key={m.id || `${m.model}-${i}`}
              type="button"
              role="menuitemradio"
              aria-checked={i === 0}
              className={`composer-model-menu-item${i === 0 ? " is-current" : ""}`}
              disabled={savingIndex != null}
              onClick={() => void pick(i)}
            >
              <span className="composer-model-menu-name">{modelName(m)}</span>
              {i === 0 && <span className="composer-model-menu-badge">当前</span>}
              {savingIndex === i && (
                <span className="composer-model-menu-saving">切换中…</span>
              )}
            </button>
          ))
        )}
      </FixedOverflowMenu>
    </>
  );
}
