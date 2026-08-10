import { useEffect, useRef, useState } from "react";
import { getSettings } from "../api";

/**
 * 进入应用后若主 API Key 未配置，打开设置并展示引导（同会话只自动弹一次）。
 */
export function useLlmSetupGuide(): {
  settingsOpen: boolean;
  setSettingsOpen: (open: boolean) => void;
  llmSetupGuide: boolean;
  clearLlmSetupGuide: () => void;
} {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [llmSetupGuide, setLlmSetupGuide] = useState(false);
  const promptedRef = useRef(false);

  useEffect(() => {
    if (promptedRef.current) return;
    promptedRef.current = true;
    getSettings()
      .then((data) => {
        if (data.llm_api_key_configured === false) {
          setLlmSetupGuide(true);
          setSettingsOpen(true);
        }
      })
      .catch(() => {
        /* 设置拉取失败时不阻断主界面 */
      });
  }, []);

  return {
    settingsOpen,
    setSettingsOpen,
    llmSetupGuide,
    clearLlmSetupGuide: () => setLlmSetupGuide(false),
  };
}
