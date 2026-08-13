import { useRef } from "react";
import { downloadUrl, isMarkdownPath, type SourceRef } from "../api";
import { pathBasename } from "../utils/kbPath";
import { SKILLS_DIR } from "../utils/fileTree";
import type { useComposerDocState } from "./useComposerDocState";
import type { useDocPreviewLayout } from "./app/useDocPreviewLayout";

type Composer = ReturnType<typeof useComposerDocState>;
type DocLayout = ReturnType<typeof useDocPreviewLayout>;

type Options = {
  composer: Composer;
  doc: DocLayout;
  refreshSidebar: () => void;
  /** 仅顶层「技能」目录：打开启用集，不进托盘 */
  onOpenEnabledSkills: () => void;
  /** search 出处由 shell 打开 snippet modal */
  onSearchSource?: (src: Extract<SourceRef, { type: "search" }>) => void;
};

/**
 * 文档托盘 ↔ float/pin 预览编排 seam（对称于 useEnabledSkillsAttach）。
 * App 只接线 shell，不堆 pin/tray/路径同步状态机。
 */
export function useComposerPreviewBridge({
  composer,
  doc,
  refreshSidebar,
  onOpenEnabledSkills,
  onSearchSource,
}: Options) {
  const pinAddedTrayRef = useRef<string | null>(null);

  function addDocToComposer(
    path: string,
    { setAsPrimary }: { setAsPrimary: boolean },
  ) {
    const title = pathBasename(path);
    if (!composer.items.some((i) => i.path === path)) {
      composer.addDocumentToTray(path, title);
    }
    if (setAsPrimary && isMarkdownPath(path)) {
      composer.setPrimary(path);
    }
  }

  function openDocWithComposer(
    path: string,
    excerpt?: string,
    options?: { pin?: boolean },
  ) {
    addDocToComposer(path, { setAsPrimary: true });
    doc.openDocPreview(path, excerpt, options);
  }

  function handlePinDoc() {
    const path = doc.floatPath;
    if (!path) return;
    const wasInTray = composer.items.some((i) => i.path === path);
    if (!wasInTray) {
      pinAddedTrayRef.current = path;
      addDocToComposer(path, { setAsPrimary: true });
    } else {
      pinAddedTrayRef.current = null;
      if (isMarkdownPath(path)) composer.setPrimary(path);
    }
    doc.pinDocPreview();
  }

  function handleUnpinDoc() {
    const path = doc.pinnedPath;
    if (path && pinAddedTrayRef.current === path) {
      composer.removeFromTray(path);
      pinAddedTrayRef.current = null;
    }
    doc.unpinDocPreview();
  }

  function handleSelectFile(
    path: string,
    mods?: { ctrlKey?: boolean; metaKey?: boolean },
  ) {
    if (mods?.ctrlKey || mods?.metaKey) {
      addDocToComposer(path, { setAsPrimary: false });
      return;
    }
    if (!isMarkdownPath(path)) {
      window.open(downloadUrl(path), "_blank", "noopener,noreferrer");
      return;
    }
    doc.openDocPreview(path, undefined, { pin: false });
  }

  function handleSelectFolder(
    path: string,
    mods?: { ctrlKey?: boolean; metaKey?: boolean },
  ) {
    if (!(mods?.ctrlKey || mods?.metaKey)) return;
    if (path === SKILLS_DIR) {
      onOpenEnabledSkills();
      return;
    }
    addDocToComposer(path, { setAsPrimary: false });
  }

  function handleKbPathChanged(fromPath: string, toPath: string) {
    composer.remapPath(fromPath, toPath);
    doc.remapOpenPath(fromPath, toPath);
    refreshSidebar();
  }

  function handleKbPathsDeleted(paths: string[]) {
    const deleted = new Set(paths);
    for (const p of composer.items.map((i) => i.path)) {
      if (deleted.has(p)) composer.removeFromTray(p);
    }
    if (doc.floatPath && deleted.has(doc.floatPath)) doc.closeFloatPreview();
    if (doc.pinnedPath && deleted.has(doc.pinnedPath)) doc.closePinnedPreview();
    refreshSidebar();
  }

  function handleTraySetPrimary(path: string) {
    if (!isMarkdownPath(path)) return;
    if (!composer.items.some((i) => i.path === path)) return;
    composer.setPrimary(path);
    openDocWithComposer(path, undefined, { pin: true });
  }

  function handleTrayRemove(path: string) {
    const wasPinned = doc.pinnedPath === path;
    composer.removeFromTray(path);
    if (wasPinned) doc.closePinnedPreview();
  }

  function handleOpenSource(src: SourceRef) {
    if (src.type === "search") {
      onSearchSource?.(src);
      return;
    }
    if (src.type === "kb") {
      openDocWithComposer(src.path, src.excerpt, { pin: true });
      return;
    }
    if (src.type === "web") {
      window.open(src.url, "_blank", "noopener,noreferrer");
    }
  }

  return {
    openDocWithComposer,
    handlePinDoc,
    handleUnpinDoc,
    handleSelectFile,
    handleSelectFolder,
    handleKbPathChanged,
    handleKbPathsDeleted,
    handleTraySetPrimary,
    handleTrayRemove,
    handleOpenSource,
  };
}
