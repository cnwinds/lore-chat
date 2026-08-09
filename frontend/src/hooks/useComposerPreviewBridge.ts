import { useRef, useState } from "react";
import { downloadUrl, isMarkdownPath, type SourceRef } from "../api";
import type { useComposerDocState } from "./useComposerDocState";
import type { useDocPreviewLayout } from "./app/useDocPreviewLayout";
import { isInsideSkillPackage } from "../utils/kbSkill";

type Composer = ReturnType<typeof useComposerDocState>;
type DocLayout = ReturnType<typeof useDocPreviewLayout>;

type Options = {
  composer: Composer;
  doc: DocLayout;
  refreshSidebar: () => void;
  /** search 出处由 shell 打开 snippet modal */
  onSearchSource?: (src: Extract<SourceRef, { type: "search" }>) => void;
};

/**
 * 文档托盘 ↔ float/pin 预览编排 seam（对称于 useSkillTrayAttach）。
 * App 只接线 shell，不堆 pin/tray/路径同步状态机。
 */
export function useComposerPreviewBridge({
  composer,
  doc,
  refreshSidebar,
  onSearchSource,
}: Options) {
  const pinAddedTrayRef = useRef<string | null>(null);
  const [kbDocs, setKbDocs] = useState<string[]>([]);

  function addDocToComposer(path: string) {
    const title = path.split("/").pop() ?? path;
    if (!composer.items.some((i) => i.path === path)) {
      composer.addDocumentToTray(path, title);
    }
    composer.setPrimary(path);
  }

  function openDocWithComposer(
    path: string,
    excerpt?: string,
    options?: { pin?: boolean },
  ) {
    addDocToComposer(path);
    doc.openDocPreview(path, excerpt, options);
  }

  function handlePinDoc() {
    const path = doc.floatPath;
    if (!path) return;
    const wasInTray = composer.items.some((i) => i.path === path);
    if (!wasInTray) {
      pinAddedTrayRef.current = path;
      addDocToComposer(path);
    } else {
      pinAddedTrayRef.current = null;
      composer.setPrimary(path);
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
    mods?: { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean },
  ) {
    const title = path.split("/").pop() ?? path;
    if (!isMarkdownPath(path)) {
      window.open(downloadUrl(path), "_blank", "noopener,noreferrer");
      return;
    }
    if (mods?.ctrlKey || mods?.metaKey || mods?.shiftKey) {
      if (isInsideSkillPackage(path, kbDocs)) {
        window.alert("Skill 包内文档请点文件夹附加 Skill；此处仅可打开阅读。");
        return;
      }
      composer.addDocumentToTray(path, title);
    } else {
      doc.openDocPreview(path, undefined, { pin: false });
    }
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
    const item = composer.items.find((i) => i.path === path);
    if (!item || item.kind !== "document") return;
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
    setKbDocs,
    openDocWithComposer,
    handlePinDoc,
    handleUnpinDoc,
    handleSelectFile,
    handleKbPathChanged,
    handleKbPathsDeleted,
    handleTraySetPrimary,
    handleTrayRemove,
    handleOpenSource,
  };
}
