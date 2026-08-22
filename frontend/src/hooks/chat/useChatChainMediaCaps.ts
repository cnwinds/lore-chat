import { useCallback, useEffect, useState } from "react";
import { getSettings } from "../../api";
import { resolveChainMediaCapsFromSettings } from "../../utils/chatChainMedia";
import { SETTINGS_CHANGED_EVENT } from "../../utils/settingsChangedEvent";

export function useChatChainMediaCaps() {
  const [videoSupported, setVideoSupported] = useState(false);
  const [maxVideos, setMaxVideos] = useState(1);
  const [imageSupported, setImageSupported] = useState(false);
  const [maxImages, setMaxImages] = useState<number | null>(null);
  const [videoWireData, setVideoWireData] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await getSettings();
      const caps = await resolveChainMediaCapsFromSettings(data.chat_models);
      setVideoSupported(caps.videoSupported);
      setMaxVideos(caps.maxVideos);
      setImageSupported(caps.imageSupported);
      setMaxImages(caps.maxImages);
      setVideoWireData(caps.videoWireData);
    } catch {
      setVideoSupported(false);
      setMaxVideos(1);
      setImageSupported(false);
      setMaxImages(null);
      setVideoWireData(false);
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

  return {
    videoSupported,
    maxVideos,
    imageSupported,
    maxImages,
    videoWireData,
    refresh,
  };
}
