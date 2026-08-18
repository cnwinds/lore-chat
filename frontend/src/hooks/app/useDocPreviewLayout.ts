import { useRef, useState } from "react";
import type { DocWidth, RefreshKbOpts } from "../../types/doc";
import {
  getStoredFloatWidth,
  getStoredPanelWidth,
  setStoredFloatWidth,
  setStoredPanelWidth,
} from "../../utils/docStorage";
import { isMediaPath, MEDIA_ROOT, normalizeKbRel } from "../../utils/kbMediaPaths";
import { remapKbPath } from "../../utils/remapKbPath";

function pathTouchesChanged(path: string | null, changedPath?: string): boolean {
  return Boolean(
    path &&
      (!changedPath ||
        changedPath === path ||
        path.startsWith(`${changedPath}/`) ||
        // 打开的是目录时：目录内文件变更也需刷新（媒体图库）
        changedPath.startsWith(`${path}/`)),
  );
}

/** 供单测与外部复用 */
export { pathTouchesChanged };

export function useDocPreviewLayout(refreshSidebar: () => void) {
  const [floatPath, setFloatPath] = useState<string | null>(null);
  const [floatHighlight, setFloatHighlight] = useState<string | undefined>();
  const [floatWidth, setFloatWidth] = useState<DocWidth>(() => getStoredFloatWidth());
  const [floatFocus, setFloatFocus] = useState(false);
  const [floatRefreshKey, setFloatRefreshKey] = useState(0);

  const [pinnedPath, setPinnedPath] = useState<string | null>(null);
  const [pinnedHighlight, setPinnedHighlight] = useState<string | undefined>();
  const [pinnedWidth, setPinnedWidth] = useState<DocWidth>(() => getStoredPanelWidth());
  const [pinnedFocus, setPinnedFocus] = useState(false);
  const [pinnedRefreshKey, setPinnedRefreshKey] = useState(0);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mediaFolderPath, setMediaFolderPath] = useState<string | null>(null);
  const [mediaRefreshKey, setMediaRefreshKey] = useState(0);
  const [memoryPanelOpen, setMemoryPanelOpen] = useState(false);
  const floatCloseRef = useRef<(() => void) | null>(null);
  const pinnedCloseRef = useRef<(() => void) | null>(null);

  function bindFloatClose(handler: (() => void) | null) {
    floatCloseRef.current = handler;
  }

  function bindPinnedClose(handler: (() => void) | null) {
    pinnedCloseRef.current = handler;
  }

  function closeFloatPreview() {
    setFloatPath(null);
    setFloatHighlight(undefined);
    setFloatFocus(false);
    if (!pinnedFocus) setSidebarCollapsed(false);
  }

  function closePinnedPreview() {
    setPinnedPath(null);
    setPinnedHighlight(undefined);
    setPinnedFocus(false);
    if (!floatFocus) setSidebarCollapsed(false);
  }

  function closeAllPreviews() {
    setFloatPath(null);
    setFloatHighlight(undefined);
    setFloatFocus(false);
    setPinnedPath(null);
    setPinnedHighlight(undefined);
    setPinnedFocus(false);
    setMediaFolderPath(null);
    setMemoryPanelOpen(false);
    setSidebarCollapsed(false);
  }

  function closeMediaFolder() {
    setMediaFolderPath(null);
  }

  function closeMemoryPanel() {
    setMemoryPanelOpen(false);
  }

  /** 打开媒体目录图库（聊天区左侧浮窗，与文档浮窗同槽；保留右侧 pinned）。 */
  function openMediaFolder(path: string) {
    const norm = normalizeKbRel(path);
    if (!norm || norm === MEDIA_ROOT || !isMediaPath(norm)) return;
    if (mediaFolderPath === norm) {
      closeMediaFolder();
      return;
    }
    setFloatPath(null);
    setFloatHighlight(undefined);
    setFloatFocus(false);
    setMemoryPanelOpen(false);
    setMediaFolderPath(norm);
    // 图库默认宽浮窗，便于瓦片排布（不持久化，避免覆盖文档浮窗偏好）
    setFloatWidth("wide");
  }

  /** 打开长期画像浮窗（与媒体/文档浮窗同槽；保留右侧 pinned）。 */
  function openMemoryPanel() {
    if (memoryPanelOpen) {
      closeMemoryPanel();
      return;
    }
    setFloatPath(null);
    setFloatHighlight(undefined);
    setFloatFocus(false);
    setMediaFolderPath(null);
    setMemoryPanelOpen(true);
    setFloatWidth("wide");
  }

  function requestCloseFloatPreview() {
    if (floatCloseRef.current) floatCloseRef.current();
    else closeFloatPreview();
  }

  function requestClosePinnedPreview() {
    if (pinnedCloseRef.current) pinnedCloseRef.current();
    else closePinnedPreview();
  }

  function refreshKb(changedPath?: string, opts?: RefreshKbOpts) {
    refreshSidebar();
    if (
      opts?.except !== "float" &&
      pathTouchesChanged(floatPath, changedPath)
    ) {
      setFloatRefreshKey((k) => k + 1);
    }
    if (
      opts?.except !== "pinned" &&
      pathTouchesChanged(pinnedPath, changedPath)
    ) {
      setPinnedRefreshKey((k) => k + 1);
    }
    if (pathTouchesChanged(mediaFolderPath, changedPath)) {
      setMediaRefreshKey((k) => k + 1);
    }
  }

  function openDocPreview(
    path: string,
    excerpt?: string,
    options?: { pin?: boolean },
  ) {
    const wantPin = options?.pin ?? false;

    if (wantPin) {
      setMediaFolderPath(null);
      setMemoryPanelOpen(false);
      setPinnedPath(path);
      setPinnedHighlight(excerpt);
      setPinnedWidth(getStoredPanelWidth());
      return;
    }

    if (path === floatPath) {
      requestCloseFloatPreview();
      return;
    }

    setMediaFolderPath(null);
    setMemoryPanelOpen(false);
    setFloatPath(path);
    setFloatHighlight(excerpt);
    setFloatFocus(false);
    setFloatWidth(getStoredFloatWidth());
  }

  function pinDocPreview() {
    if (!floatPath) return;
    setMediaFolderPath(null);
    setMemoryPanelOpen(false);
    setPinnedPath(floatPath);
    setPinnedHighlight(floatHighlight);
    setPinnedWidth(getStoredPanelWidth());
    closeFloatPreview();
  }

  function unpinDocPreview() {
    if (!pinnedPath) return;
    setMediaFolderPath(null);
    setMemoryPanelOpen(false);
    setFloatPath(pinnedPath);
    setFloatHighlight(pinnedHighlight);
    setFloatFocus(false);
    setFloatWidth(getStoredFloatWidth());
    closePinnedPreview();
  }

  function enterFloatFocus() {
    setFloatFocus(true);
    setSidebarCollapsed(true);
  }

  function exitFloatFocus() {
    setFloatFocus(false);
    if (!pinnedFocus) setSidebarCollapsed(false);
  }

  function enterPinnedFocus() {
    setPinnedFocus(true);
    setSidebarCollapsed(true);
  }

  function exitPinnedFocus() {
    setPinnedFocus(false);
    if (!floatFocus) setSidebarCollapsed(false);
  }

  function toggleFloatWidth() {
    setFloatWidth((w) => {
      const next = w === "narrow" ? "wide" : "narrow";
      setStoredFloatWidth(next);
      return next;
    });
  }

  function togglePinnedWidth() {
    setPinnedWidth((w) => {
      const next = w === "narrow" ? "wide" : "narrow";
      setStoredPanelWidth(next);
      return next;
    });
  }

  function toggleFloatFocus() {
    if (floatFocus) exitFloatFocus();
    else enterFloatFocus();
  }

  function togglePinnedFocus() {
    if (pinnedFocus) exitPinnedFocus();
    else enterPinnedFocus();
  }

  function remapOpenPath(from: string, to: string) {
    if (floatPath) {
      const next = remapKbPath(floatPath, from, to);
      if (next !== floatPath) {
        setFloatPath(next);
        setFloatRefreshKey((k) => k + 1);
      }
    }
    if (pinnedPath) {
      const next = remapKbPath(pinnedPath, from, to);
      if (next !== pinnedPath) {
        setPinnedPath(next);
        setPinnedRefreshKey((k) => k + 1);
      }
    }
    if (mediaFolderPath) {
      const next = remapKbPath(mediaFolderPath, from, to);
      if (next !== mediaFolderPath) {
        setMediaFolderPath(next);
        setMediaRefreshKey((k) => k + 1);
      }
    }
  }

  const showFloat = Boolean(floatPath);
  const showPinned = Boolean(pinnedPath);
  const showMediaGallery = Boolean(mediaFolderPath);
  const showMemoryPanel = memoryPanelOpen;
  const panelFocus = Boolean(pinnedFocus && pinnedPath);
  const floatFocusActive = Boolean(floatFocus && floatPath);
  const mainFloatWide = Boolean(
    ((floatPath && !floatFocus) || mediaFolderPath || memoryPanelOpen) &&
      floatWidth === "wide",
  );

  return {
    floatPath,
    setFloatPath,
    floatHighlight,
    floatWidth,
    floatRefreshKey,
    pinnedPath,
    setPinnedPath,
    pinnedHighlight,
    pinnedWidth,
    pinnedFocus,
    pinnedRefreshKey,
    mediaFolderPath,
    mediaRefreshKey,
    memoryPanelOpen,
    /** 聊天来源高亮用右侧栏文档 */
    previewPath: pinnedPath,
    sidebarCollapsed,
    setSidebarCollapsed,
    bindFloatClose,
    bindPinnedClose,
    requestCloseFloatPreview,
    requestClosePinnedPreview,
    closeFloatPreview,
    closePinnedPreview,
    closeMediaFolder,
    closeMemoryPanel,
    closeAllPreviews,
    refreshKb,
    remapOpenPath,
    openDocPreview,
    openMediaFolder,
    openMemoryPanel,
    pinDocPreview,
    unpinDocPreview,
    toggleFloatWidth,
    togglePinnedWidth,
    toggleFloatFocus,
    togglePinnedFocus,
    exitFloatFocus,
    exitPinnedFocus,
    panelFocus,
    floatFocus: floatFocusActive,
    showFloat,
    showPinned,
    showMediaGallery,
    showMemoryPanel,
    mainFloatWide,
    contextValue: {
      previewPath: pinnedPath,
      openDoc: openDocPreview,
      closeDoc: closePinnedPreview,
      refreshKb,
    },
  };
}
