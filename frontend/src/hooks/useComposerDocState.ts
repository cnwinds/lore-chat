import { useCallback, useState } from "react";
import { remapKbPath, remapKbPathNullable } from "../utils/remapKbPath";
import { isMarkdownPath, pathBasename } from "../utils/kbPath";
import type { ComposerDocState, DocTrayItem } from "../types/composer";
import { COMPOSER_TRAY_MAX } from "../types/composer";

export function useComposerDocState() {
  const [state, setState] = useState<ComposerDocState>({
    items: [],
    primaryPath: null,
  });

  const { items, primaryPath } = state;
  const paths = items.map((i) => i.path);

  const replaceTray = useCallback((path: string, title: string) => {
    setState({
      items: [{ path, title }],
      primaryPath: isMarkdownPath(path) ? path : null,
    });
  }, []);

  const addDocumentToTray = useCallback((path: string, title?: string) => {
    setState((prev) => {
      if (prev.items.some((i) => i.path === path)) return prev;
      if (prev.items.length >= COMPOSER_TRAY_MAX) {
        window.alert(`托盘最多 ${COMPOSER_TRAY_MAX} 项`);
        return prev;
      }
      if (prev.items.length >= COMPOSER_TRAY_MAX - 1) {
        window.alert("已选较多，模型将优先读取大纲");
      }
      const item: DocTrayItem = {
        path,
        title: title ?? pathBasename(path),
      };
      return { ...prev, items: [...prev.items, item] };
    });
  }, []);

  const removeFromTray = useCallback((path: string) => {
    setState((prev) => {
      const next = prev.items.filter((i) => i.path !== path);
      let nextPrimary = prev.primaryPath;
      if (prev.primaryPath === path) {
        nextPrimary =
          next.find((i) => isMarkdownPath(i.path))?.path ?? null;
      }
      return { items: next, primaryPath: nextPrimary };
    });
  }, []);

  const setPrimary = useCallback((path: string) => {
    setState((prev) => {
      if (!isMarkdownPath(path)) return prev;
      if (!prev.items.some((i) => i.path === path)) return prev;
      return { ...prev, primaryPath: path };
    });
  }, []);

  const remapPath = useCallback((from: string, to: string) => {
    setState((prev) => {
      const nextItems = prev.items.map((i) => {
        const path = remapKbPath(i.path, from, to);
        if (path === i.path) return i;
        return { ...i, path, title: pathBasename(path) };
      });
      let primaryPath = remapKbPathNullable(prev.primaryPath, from, to);
      if (primaryPath && !isMarkdownPath(primaryPath)) {
        primaryPath =
          nextItems.find((i) => isMarkdownPath(i.path))?.path ?? null;
      }
      return { items: nextItems, primaryPath };
    });
  }, []);

  const docContextItems = items.map((i) => ({
    path: i.path,
    kind: "document" as const,
  }));

  return {
    items,
    primaryPath,
    paths,
    docContextItems,
    replaceTray,
    addDocumentToTray,
    removeFromTray,
    setPrimary,
    remapPath,
  };
}
