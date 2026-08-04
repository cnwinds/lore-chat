import { useRef, useState } from "react";
import type { DocWidth } from "../../types/doc";
import {
  getStoredFloatWidth,
  getStoredPanelWidth,
  setStoredFloatWidth,
  setStoredPanelWidth,
} from "../../utils/docStorage";

function pathTouchesChanged(path: string | null, changedPath?: string): boolean {
  return Boolean(
    path &&
      (!changedPath || changedPath === path || path.startsWith(`${changedPath}/`)),
  );
}

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
    setSidebarCollapsed(false);
  }

  function requestCloseFloatPreview() {
    if (floatCloseRef.current) floatCloseRef.current();
    else closeFloatPreview();
  }

  function requestClosePinnedPreview() {
    if (pinnedCloseRef.current) pinnedCloseRef.current();
    else closePinnedPreview();
  }

  function refreshKb(changedPath?: string) {
    refreshSidebar();
    if (pathTouchesChanged(floatPath, changedPath)) {
      setFloatRefreshKey((k) => k + 1);
    }
    if (pathTouchesChanged(pinnedPath, changedPath)) {
      setPinnedRefreshKey((k) => k + 1);
    }
  }

  function openDocPreview(
    path: string,
    excerpt?: string,
    options?: { pin?: boolean },
  ) {
    const wantPin = options?.pin ?? false;

    if (wantPin) {
      setPinnedPath(path);
      setPinnedHighlight(excerpt);
      setPinnedWidth(getStoredPanelWidth());
      return;
    }

    if (path === floatPath) {
      requestCloseFloatPreview();
      return;
    }

    setFloatPath(path);
    setFloatHighlight(excerpt);
    setFloatFocus(false);
    setFloatWidth(getStoredFloatWidth());
  }

  function pinDocPreview() {
    if (!floatPath) return;
    setPinnedPath(floatPath);
    setPinnedHighlight(floatHighlight);
    setPinnedWidth(getStoredPanelWidth());
    closeFloatPreview();
  }

  function unpinDocPreview() {
    if (!pinnedPath) return;
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
    if (floatPath === from) {
      setFloatPath(to);
      setFloatRefreshKey((k) => k + 1);
    }
    if (pinnedPath === from) {
      setPinnedPath(to);
      setPinnedRefreshKey((k) => k + 1);
    }
  }

  const showFloat = Boolean(floatPath);
  const showPinned = Boolean(pinnedPath);
  const panelFocus = Boolean(pinnedFocus && pinnedPath);
  const floatFocusActive = Boolean(floatFocus && floatPath);
  const mainFloatWide = Boolean(
    floatPath && floatWidth === "wide" && !floatFocus,
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
    closeAllPreviews,
    refreshKb,
    remapOpenPath,
    openDocPreview,
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
    mainFloatWide,
    contextValue: {
      previewPath: pinnedPath,
      openDoc: openDocPreview,
      closeDoc: closePinnedPreview,
      refreshKb,
    },
  };
}
