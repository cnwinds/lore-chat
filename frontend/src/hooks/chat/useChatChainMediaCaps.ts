import { useCallback, useEffect, useState } from "react";
import { getSettings } from "../../api";
import { resolveChainMediaCapsFromSettings } from "../../utils/chatChainMedia";
import { SETTINGS_CHANGED_EVENT } from "../../utils/settingsChangedEvent";

export function useChatChainMediaCaps() {
  const [videoSupported, setVideoSupported] = useState(false);
  const [maxVideos, setMaxVideos] = useState(1);

  const refresh = useCallback(async () => {
    try {
      const data = await getSettings();
      const models = data.chat_models;
      const caps = await resolveChainMediaCapsFromSettings(models);
      setVideoSupported(caps.videoSupported);
      setMaxVideos(caps.maxVideos);
    } catch {
      setVideoSupported(false);
      setMaxVideos(1);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const onSettingsChanged = () => {
      void refresh();
    };
    window.addEventListener(SETTINGS_CHANGED_EVENT, onSettingsChanged);
    return () => {
      window.removeEventListener(SETTINGS_CHANGED_EVENT, onSettingsChanged);
    };
  }, [refresh]);

  return { videoSupported, maxVideos, refresh };
}
