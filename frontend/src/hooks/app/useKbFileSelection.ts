import { useRef, useState } from "react";
import { isSystemLayerPath } from "../../utils/fileTree";

export function useKbFileSelection() {
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const [docs, setDocs] = useState<string[]>([]);
  const lastSelectedPathRef = useRef<string | null>(null);

  function clearSelection() {
    setSelectedPaths(new Set());
    lastSelectedPathRef.current = null;
  }

  function toggleSelectionMode() {
    setSelectionMode((prev) => {
      if (prev) clearSelection();
      return !prev;
    });
  }

  function handleToggleSelect(path: string, shiftKey?: boolean) {
    if (isSystemLayerPath(path)) return;
    setSelectedPaths((prev) => {
      const next = new Set(prev);
      const sameFolder = (a: string, b: string) =>
        a.slice(0, Math.max(0, a.lastIndexOf("/"))) ===
        b.slice(0, Math.max(0, b.lastIndexOf("/")));
      const lastPath = lastSelectedPathRef.current;
      if (shiftKey && lastPath && sameFolder(lastPath, path)) {
        const folder = path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";
        const folderDocs = docs
          .filter((p) => {
            if (isSystemLayerPath(p)) return false;
            const currentFolder = p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : "";
            return currentFolder === folder;
          })
          .sort((a, b) => a.localeCompare(b, "zh-CN"));
        const start = folderDocs.indexOf(lastPath);
        const end = folderDocs.indexOf(path);
        if (start >= 0 && end >= 0) {
          const [from, to] = start < end ? [start, end] : [end, start];
          folderDocs.slice(from, to + 1).forEach((p) => next.add(p));
          lastSelectedPathRef.current = path;
          return next;
        }
      }
      if (next.has(path)) next.delete(path);
      else next.add(path);
      lastSelectedPathRef.current = path;
      return next;
    });
  }

  function handleSelectFolderAll(paths: string[]) {
    if (paths.length === 0) return;
    setSelectedPaths((prev) => {
      const next = new Set(prev);
      paths.forEach((path) => {
        if (!isSystemLayerPath(path)) next.add(path);
      });
      return next;
    });
  }

  return {
    selectionMode,
    setSelectionMode,
    selectedPaths,
    docs,
    setDocs,
    clearSelection,
    toggleSelectionMode,
    handleToggleSelect,
    handleSelectFolderAll,
  };
}
