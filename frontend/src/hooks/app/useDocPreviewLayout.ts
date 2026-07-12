import { useRef, useState } from "react";
import type { DocWidth } from "../../types/doc";

export function useDocPreviewLayout(refreshSidebar: () => void) {
  const [docRefreshKey, setDocRefreshKey] = useState(0);
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [highlightText, setHighlightText] = useState<string | undefined>();
  const [docWidth, setDocWidth] = useState<DocWidth>("narrow");
  const [docPinned, setDocPinned] = useState(false);
  const [docFocus, setDocFocus] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const docCloseRef = useRef<(() => void) | null>(null);
  const closeDocPreviewRef = useRef<(() => void) | null>(null);

  function bindDocClose(handler: (() => void) | null) {
    docCloseRef.current = handler;
  }

  function closeDocPreview() {
    setPreviewPath(null);
    setHighlightText(undefined);
    setDocPinned(false);
    setDocFocus(false);
    setSidebarCollapsed(false);
    // docWidth intentionally retained
  }
  closeDocPreviewRef.current = closeDocPreview;

  function requestCloseDocPreview() {
    if (docCloseRef.current) docCloseRef.current();
    else closeDocPreview();
  }

  function refreshKb(changedPath?: string) {
    refreshSidebar();
    if (
      previewPath &&
      (!changedPath ||
        changedPath === previewPath ||
        previewPath.startsWith(`${changedPath}/`))
    ) {
      setDocRefreshKey((k) => k + 1);
    }
  }

  function openDocPreview(
    path: string,
    excerpt?: string,
    options?: { pin?: boolean },
  ) {
    const wantPin = options?.pin;

    if (path === previewPath && !docPinned && wantPin !== true) {
      requestCloseDocPreview();
      return;
    }

    setPreviewPath(path);
    setHighlightText(excerpt);

    if (wantPin === true) {
      setDocPinned(true);
    } else if (wantPin === false) {
      setDocPinned(false);
      setDocFocus(false);
    } else if (!docPinned) {
      setDocPinned(false);
      setDocFocus(false);
    }
  }

  function pinDocPreview() {
    if (!previewPath) return;
    setDocPinned(true);
  }

  function unpinDocPreview() {
    if (!previewPath) return;
    setDocPinned(false);
    setDocFocus(false);
    setSidebarCollapsed(false);
  }

  function enterDocFocus() {
    setDocFocus(true);
    setSidebarCollapsed(true);
  }

  function exitDocFocus() {
    setDocFocus(false);
    setSidebarCollapsed(false);
  }

  function toggleDocWidth() {
    setDocWidth((w) => (w === "narrow" ? "wide" : "narrow"));
  }

  function toggleDocFocus() {
    if (docFocus) exitDocFocus();
    else enterDocFocus();
  }

  const floatFocus = docFocus && previewPath && !docPinned;
  const panelFocus = docFocus && previewPath && docPinned;
  const showFloat = Boolean(previewPath && !docPinned);
  const showPinned = Boolean(previewPath && docPinned);
  const mainFloatWide = Boolean(
    previewPath && !docPinned && docWidth === "wide" && !docFocus,
  );

  return {
    previewPath,
    setPreviewPath,
    highlightText,
    docRefreshKey,
    setDocRefreshKey,
    docWidth,
    docPinned,
    docFocus,
    sidebarCollapsed,
    setSidebarCollapsed,
    bindDocClose,
    requestCloseDocPreview,
    refreshKb,
    openDocPreview,
    pinDocPreview,
    unpinDocPreview,
    closeDocPreview: () => closeDocPreviewRef.current?.(),
    toggleDocWidth,
    toggleDocFocus,
    exitDocFocus,
    floatFocus,
    panelFocus,
    showFloat,
    showPinned,
    mainFloatWide,
    contextValue: {
      previewPath,
      openDoc: openDocPreview,
      closeDoc: closeDocPreview,
      refreshKb,
    },
  };
}
