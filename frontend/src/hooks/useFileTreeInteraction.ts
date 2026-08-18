import { useCallback, useRef, useState, type DragEvent } from "react";
import { isKbFolderMoveInvalid } from "../utils/kbTreeMove";
import { downloadKbDirectory, downloadUrl } from "../api";
import type { FileTreeNodeContext } from "../components/FileTree";
import { isProtectedKbPath } from "../utils/fileTree";
import {
  collectDroppedFiles,
  dropEffectForTransfer,
} from "../utils/droppedFiles";
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
  const [externalFileDrag, setExternalFileDrag] = useState(false);
  const [internalKbDrag, setInternalKbDrag] = useState(false);
  const externalDragDepthRef = useRef(0);
  const [renamingPath, setRenamingPath] = useState<string | null>(null);
  const [renamingValue, setRenamingValue] = useState("");
  const [menu, setMenu] = useState<KbTreeContextMenu | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  const startRename = useCallback((path: string, name: string) => {
    if (isProtectedKbPath(path)) return;
    setRenamingPath(path);
    setRenamingValue(name);
  }, []);

  const commitRename = useCallback(async () => {
    if (!renamingPath) return;
    const trimmed = renamingValue.trim();
    const from = renamingPath;
    setRenamingPath(null);
    if (!trimmed || trimmed === from.split("/").pop()) return;
    const newPath = await kb.renameEntry(from, trimmed);
    if (newPath && newPath !== from) {
      onKbPathChanged?.(from, newPath);
    }
  }, [kb, onKbPathChanged, renamingPath, renamingValue]);

  const openContextMenu = useCallback(
    (e: React.MouseEvent, ctx: FileTreeNodeContext) => {
      if (isProtectedKbPath(ctx.path) && ctx.kind === "folder") return;
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

      if (action === "download") {
        if (ctx.kind === "file") {
          window.open(
            downloadUrl(path, { download: true }),
            "_blank",
            "noopener,noreferrer",
          );
        } else {
          try {
            await downloadKbDirectory(path);
          } catch (e) {
            window.alert(e instanceof Error ? e.message : "下载失败");
          }
        }
        return;
      }
      if (action === "rename") {
        startRename(path, ctx.node.name);
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

  const clearExternalDrag = useCallback(() => {
    externalDragDepthRef.current = 0;
    setExternalFileDrag(false);
    setDropHighlightDir(null);
  }, []);

  const finishInternalDrag = useCallback(() => {
    setInternalKbDrag(false);
    setDropHighlightDir(null);
  }, []);

  const onInternalDragStart = useCallback(() => {
    // 须在 dragStart 之后异步更新，否则重渲染会打断 HTML5 拖动
    window.requestAnimationFrame(() => {
      setInternalKbDrag(true);
    });
  }, []);

  const onInternalDragEnd = useCallback(() => {
    finishInternalDrag();
  }, [finishInternalDrag]);

  const handleFloatingRootDragOver = useCallback(
    (e: DragEvent) => {
      if (kb.busy) return;
      const files = e.dataTransfer.types.includes("Files");
      const kbPath =
        e.dataTransfer.types.includes("text/kb-path") ||
        e.dataTransfer.types.includes("text/plain");
      if (!files && !kbPath) return;
      e.preventDefault();
      e.stopPropagation();
      e.dataTransfer.dropEffect = dropEffectForTransfer(e.dataTransfer);
      setDropHighlightDir("");
    },
    [kb.busy],
  );

  const handleDropFiles = useCallback(
    async (dataTransfer: DataTransfer, directory: string) => {
      if (isProtectedKbPath(directory)) return;
      const items = await collectDroppedFiles(dataTransfer);
      clearExternalDrag();
      finishInternalDrag();
      if (!items.length) return;
      await kb.importMany(items, directory);
    },
    [clearExternalDrag, finishInternalDrag, kb],
  );

  const handleMovePath = useCallback(
    async (fromPath: string, toDirectory: string) => {
      if (isProtectedKbPath(fromPath) || isProtectedKbPath(toDirectory)) return;
      if (isKbFolderMoveInvalid(fromPath, toDirectory)) return;
      const base = fromPath.split("/").pop();
      if (!base) return;
      finishInternalDrag();
      const newPath = await kb.moveFile(fromPath, toDirectory, base);
      if (newPath && newPath !== fromPath) {
        onKbPathChanged?.(fromPath, newPath);
      }
    },
    [finishInternalDrag, kb, onKbPathChanged],
  );

  const handleFloatingRootDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (kb.busy) return;
      if (e.dataTransfer.types.includes("Files")) {
        void handleDropFiles(e.dataTransfer, "");
        return;
      }
      const from =
        e.dataTransfer.getData("text/kb-path") ||
        e.dataTransfer.getData("text/plain");
      if (from) void handleMovePath(from, "");
    },
    [handleDropFiles, handleMovePath, kb.busy],
  );

  const handleSectionDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      if (kb.busy) return;
      if (e.dataTransfer.types.includes("Files")) {
        void handleDropFiles(e.dataTransfer, "");
        return;
      }
      const from =
        e.dataTransfer.getData("text/kb-path") ||
        e.dataTransfer.getData("text/plain");
      if (from) void handleMovePath(from, "");
    },
    [handleDropFiles, handleMovePath, kb.busy],
  );

  const onKbSectionDragEnter = useCallback((e: DragEvent) => {
    if (!e.dataTransfer.types.includes("Files")) return;
    externalDragDepthRef.current += 1;
    window.requestAnimationFrame(() => {
      setExternalFileDrag(true);
    });
  }, []);

  const onKbSectionDragLeave = useCallback((e: DragEvent) => {
    if (!e.dataTransfer.types.includes("Files")) return;
    externalDragDepthRef.current -= 1;
    if (externalDragDepthRef.current <= 0) {
      clearExternalDrag();
    }
  }, [clearExternalDrag]);

  const fileTreeProps = {
    dropHighlightDir,
    onDropHighlightDir: setDropHighlightDir,
    onDropFiles: handleDropFiles,
    onMovePath: handleMovePath,
    onInternalDragStart,
    onInternalDragEnd,
    onContextMenu: openContextMenu,
    renamingPath,
    renamingValue,
    onRenamingValueChange: setRenamingValue,
    onRenameCommit: () => void commitRename(),
    onRenameCancel: () => setRenamingPath(null),
    onStartRename: startRename,
    disabled: kb.busy,
  };

  const closeMenu = useCallback(() => setMenu(null), []);

  const showFloatingRoot = externalFileDrag || internalKbDrag;

  return {
    menu,
    menuRef,
    closeMenu,
    handleMenuAction,
    fileTreeProps,
    externalFileDrag,
    showFloatingRoot,
    floatingRootActive: dropHighlightDir === "",
    floatingRootUploadMode: externalFileDrag,
    onFloatingRootDragOver: handleFloatingRootDragOver,
    onFloatingRootDrop: handleFloatingRootDrop,
    onKbSectionDragEnter,
    onKbSectionDragLeave,
    onRootDragOver: (e: DragEvent) => {
      if (kb.busy) return;
      const files = e.dataTransfer.types.includes("Files");
      const kbPath =
        e.dataTransfer.types.includes("text/kb-path") ||
        e.dataTransfer.types.includes("text/plain");
      if (!files && !kbPath) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = dropEffectForTransfer(e.dataTransfer);
      if (files) setDropHighlightDir("");
    },
    onRootDrop: handleSectionDrop,
  };
}
