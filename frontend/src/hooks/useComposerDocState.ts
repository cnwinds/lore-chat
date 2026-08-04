import { useCallback, useState } from "react";
import { remapKbPath, remapKbPathNullable } from "../utils/remapKbPath";
import type { ComposerDocState } from "../types/composer";

export function useComposerDocState() {
  const [state, setState] = useState<ComposerDocState>({
    items: [],
    primaryPath: null,
  });

  const { items, primaryPath } = state;
  const paths = items.map((i) => i.path);

  const replaceTray = useCallback((path: string, title: string) => {
    setState({ items: [{ path, title }], primaryPath: path });
  }, []);

  const addToTray = useCallback((path: string, title: string) => {
    setState((prev) => {
      if (prev.items.some((i) => i.path === path)) return prev;
      if (prev.items.length >= 8) {
        window.alert("已选较多，模型将优先读取大纲");
      }
      return {
        ...prev,
        items: [...prev.items, { path, title }],
      };
    });
  }, []);

  const removeFromTray = useCallback((path: string) => {
    setState((prev) => {
      const next = prev.items.filter((i) => i.path !== path);
      const nextPrimary =
        prev.primaryPath !== path ? prev.primaryPath : (next[0]?.path ?? null);
      return { items: next, primaryPath: nextPrimary };
    });
  }, []);

  const setPrimary = useCallback((path: string) => {
    setState((prev) => ({ ...prev, primaryPath: path }));
  }, []);

  const remapPath = useCallback((from: string, to: string) => {
    setState((prev) => ({
      items: prev.items.map((i) => {
        const path = remapKbPath(i.path, from, to);
        if (path === i.path) return i;
        return { ...i, path, title: path.split("/").pop() ?? path };
      }),
      primaryPath: remapKbPathNullable(prev.primaryPath, from, to),
    }));
  }, []);

  return {
    items,
    primaryPath,
    paths,
    replaceTray,
    addToTray,
    removeFromTray,
    setPrimary,
    remapPath,
  };
}
