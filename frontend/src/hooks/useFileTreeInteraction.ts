import { useCallback, useRef, useState, type DragEvent } from "react";
import { downloadUrl } from "../api";
import type { FileTreeNodeContext } from "../components/FileTree";
import { isSystemLayerPath } from "../utils/fileTree";
import type { useKbTreeActions } from "./useKbTreeActions";

type KbActions = ReturnType<typeof useKbTreeActions>;

export type KbTreeContextMenu = {
  x: number;
  y: number;
  ctx: FileTreeNodeContext;
};

type Options = {
  kb: KbActions;
  onKbPathChanged?: (fromPath: string, toPath: string) => void;
  onKbPathsDeleted?: (paths: string[]) => void;
};

/**
 * 知识库树交互 seam：拖放、重命名、右键菜单与 FileTree props 绑定。
 */
export function useFileTreeInteraction({
  kb,
  onKbPathChanged,
  onKbPathsDeleted,
}: Options) {
  const [dropHighlightDir, setDropHighlightDir] = useState<string | null>(null);
  const [renamingPath, setRenamingPath] = useState<string | null>(null);
  const [renamingValue, setRenamingValue] = useState("");
  const [menu, setMenu] = useState<KbTreeContextMenu | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const startRename = useCallback((path: string, name: string) => {
    if (isSystemLayerPath(path)) return;
    setRenamingPath(path);
    setRenamingValue(name);
  }, []);

  const commitRename = useCallback(async () => {
    if (!renamingPath) return;
    const trimmed = renamingValue.trim();
    const from = renamingPath;
    setRenamingPath(null);
    if (!trimmed || trimmed === from.split("/").pop()) return;
    const newPath = await kb.renameFile(from, trimmed);
    if (newPath && newPath !== from) {
      onKbPathChanged?.(from, newPath);
    }
  }, [kb, onKbPathChanged, renamingPath, renamingValue]);

  const openContextMenu = useCallback(
    (e: React.MouseEvent, ctx: FileTreeNodeContext) => {
      if (isSystemLayerPath(ctx.path) && ctx.kind === "folder") return;
      setMenu({ x: e.clientX, y: e.clientY, ctx });
    },
    [],
  );

  const handleMenuAction = useCallback(
    async (action: string) => {
      if (!menu) return;
      const { ctx } = menu;
      setMenu(null);
      const path = ctx.path;

      if (action === "download" && ctx.kind === "file") {
        window.open(downloadUrl(path), "_blank", "noopener,noreferrer");
        return;
      }
      if (action === "rename" && ctx.kind === "file") {
        startRename(path, ctx.node.type === "file" ? ctx.node.name : path);
        return;
      }
      if (action === "delete") {
        const label =
          ctx.kind === "folder"
            ? `确定删除文件夹「${path || "根目录"}」及其下全部文件？`
            : `确定删除「${path}」？`;
        if (!window.confirm(label)) return;
        const deleted = await kb.deletePath(path);
        onKbPathsDeleted?.(deleted);
      }
    },
    [kb, menu, onKbPathsDeleted, startRename],
  );

  const handleDropFiles = useCallback(
    async (files: FileList, directory: string) => {
      if (isSystemLayerPath(directory)) return;
      await kb.importMany(files, directory);
    },
    [kb],
  );

  const handleMovePath = useCallback(
    async (fromPath: string, toDirectory: string) => {
      if (isSystemLayerPath(fromPath) || isSystemLayerPath(toDirectory)) return;
      const base = fromPath.split("/").pop();
      if (!base) return;
      const newPath = await kb.moveFile(fromPath, toDirectory, base);
      if (newPath && newPath !== fromPath) {
        onKbPathChanged?.(fromPath, newPath);
      }
    },
    [kb, onKbPathChanged],
  );

  const handleSectionDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      setDropHighlightDir(null);
      if (kb.busy) return;
      if (e.dataTransfer.files?.length) {
        void handleDropFiles(e.dataTransfer.files, "");
      }
    },
    [handleDropFiles, kb.busy],
  );

  const fileTreeProps = {
    dropHighlightDir,
    onDropHighlightDir: setDropHighlightDir,
    onDropFiles: handleDropFiles,
    onMovePath: handleMovePath,
    onContextMenu: openContextMenu,
    renamingPath,
    renamingValue,
    onRenamingValueChange: setRenamingValue,
    onRenameCommit: () => void commitRename(),
    onRenameCancel: () => setRenamingPath(null),
    onStartRename: startRename,
    disabled: kb.busy,
  };

  const rootDropActive = dropHighlightDir === "";

  const closeMenu = useCallback(() => setMenu(null), []);

  return {
    menu,
    menuRef,
    closeMenu,
    handleMenuAction,
    fileTreeProps,
    rootDropActive,
    onRootDragOver: (e: DragEvent) => {
      if (kb.busy) return;
      e.preventDefault();
      setDropHighlightDir("");
    },
    onRootDragLeave: () => setDropHighlightDir(null),
    onRootDrop: handleSectionDrop,
  };
}
