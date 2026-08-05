import { useCallback, useState } from "react";
import { remapKbPath, remapKbPathNullable } from "../utils/remapKbPath";
import { skillRootLabel } from "../utils/kbSkill";
import type { ComposerDocState, DocTrayItem, DocTrayKind } from "../types/composer";
import { COMPOSER_TRAY_MAX } from "../types/composer";

function trayTitle(path: string, kind: DocTrayKind): string {
  if (kind === "skill_root") return skillRootLabel(path);
  return path.split("/").pop() ?? path;
}

export function useComposerDocState() {
  const [state, setState] = useState<ComposerDocState>({
    items: [],
    primaryPath: null,
  });

  const { items, primaryPath } = state;
  const paths = items.map((i) => i.path);
  const documentPaths = items.filter((i) => i.kind === "document").map((i) => i.path);

  const replaceTray = useCallback((path: string, title: string) => {
    setState({
      items: [{ path, title, kind: "document" }],
      primaryPath: path,
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
        title: title ?? trayTitle(path, "document"),
        kind: "document",
      };
      return { ...prev, items: [...prev.items, item] };
    });
  }, []);

  const addSkillRoots = useCallback((roots: string[]) => {
    setState((prev) => {
      let next = [...prev.items];
      let changed = false;
      for (const root of roots) {
        if (next.some((i) => i.path === root && i.kind === "skill_root")) {
          continue;
        }
        if (next.length >= COMPOSER_TRAY_MAX) break;
        next = [
          ...next,
          {
            path: root,
            title: skillRootLabel(root),
            kind: "skill_root" as const,
          },
        ];
        changed = true;
      }
      if (!changed) return prev;
      return { ...prev, items: next };
    });
  }, []);

  /** @deprecated use addDocumentToTray */
  const addToTray = addDocumentToTray;

  const removeFromTray = useCallback((path: string) => {
    setState((prev) => {
      const removed = prev.items.find((i) => i.path === path);
      const next = prev.items.filter((i) => i.path !== path);
      let nextPrimary = prev.primaryPath;
      if (removed?.kind === "document" && prev.primaryPath === path) {
        nextPrimary = next.find((i) => i.kind === "document")?.path ?? null;
      }
      return { items: next, primaryPath: nextPrimary };
    });
  }, []);

  const setPrimary = useCallback((path: string) => {
    setState((prev) => {
      const item = prev.items.find((i) => i.path === path);
      if (!item || item.kind !== "document") return prev;
      return { ...prev, primaryPath: path };
    });
  }, []);

  const remapPath = useCallback((from: string, to: string) => {
    setState((prev) => ({
      items: prev.items.map((i) => {
        const path = remapKbPath(i.path, from, to);
        if (path === i.path) return i;
        return {
          ...i,
          path,
          title: trayTitle(path, i.kind),
        };
      }),
      primaryPath: remapKbPathNullable(prev.primaryPath, from, to),
    }));
  }, []);

  const docContextItems = items.map((i) => ({ path: i.path, kind: i.kind }));

  return {
    items,
    primaryPath,
    paths,
    documentPaths,
    docContextItems,
    replaceTray,
    addDocumentToTray,
    addSkillRoots,
    addToTray,
    removeFromTray,
    setPrimary,
    remapPath,
    trayRemaining: Math.max(0, COMPOSER_TRAY_MAX - items.length),
  };
}
