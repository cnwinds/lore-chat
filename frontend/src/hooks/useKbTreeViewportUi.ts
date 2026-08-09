import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type RefObject,
} from "react";
import {
  buildFileTree,
  collectAncestorFolderPaths,
  nextUserExpandedAfterTreeChange,
  resolveExpandedFolderPaths,
} from "../utils/fileTree";
import {
  hasPersistedExpanded,
  loadKbTreeUi,
  saveKbTreeExpanded,
  saveKbTreeExpandedIfPersisted,
  saveKbTreeScrollTop,
} from "../utils/kbTreeUiStorage";

type Options = {
  paths: string[];
  /** 预览中打开的文件：驱动临时露出（不落盘） */
  activePaths?: string[];
  collapsed: boolean;
  scrollRef: RefObject<HTMLElement | null>;
};

/** 滚动恢复阶段：pending → restoring → idle */
type RestorePhase = "pending" | "restoring" | "idle";

const RESTORE_TIMEOUT_MS = 2000;

/**
 * 知识库树 viewport UI：展开态 + 滚动位置的 hydrate / restore / persist。
 *
 * 对外小 interface：`tree` / `expanded` / `toggleFolder`；Sidebar 只接线，FileTree 只渲染。
 */
export function useKbTreeViewportUi({
  paths,
  activePaths = [],
  collapsed,
  scrollRef,
}: Options) {
  const tree = useMemo(() => buildFileTree(paths), [paths]);
  const scrollEnabled = paths.length > 0;

  const [userExpanded, setUserExpanded] = useState<Set<string>>(() => new Set());
  const [sessionReveal, setSessionReveal] = useState<Set<string>>(
    () => new Set(),
  );
  const expanded = useMemo(() => {
    const next = new Set(userExpanded);
    for (const p of sessionReveal) next.add(p);
    return next;
  }, [userExpanded, sessionReveal]);

  const didHydrateRef = useRef(false);
  const [hydrated, setHydrated] = useState(false);

  const phaseRef = useRef<RestorePhase>("pending");
  /** 仅用户滚动（非程序恢复）后才允许落盘 */
  const allowPersistRef = useRef(false);

  // —— 展开：hydrate / 树变更剪枝 / 打开文件临时露出 ——
  useEffect(() => {
    if (tree.length === 0) return;

    if (!didHydrateRef.current) {
      didHydrateRef.current = true;
      const stored = loadKbTreeUi();
      setUserExpanded(
        new Set(resolveExpandedFolderPaths(tree, stored?.expandedPaths)),
      );
      setSessionReveal(new Set());
      setHydrated(true);
      return;
    }

    const persisted = hasPersistedExpanded();
    setUserExpanded((prev) => {
      const nextPaths = nextUserExpandedAfterTreeChange(tree, prev, persisted);
      if (
        nextPaths.length === prev.size &&
        nextPaths.every((p) => prev.has(p))
      ) {
        return prev;
      }
      if (persisted) saveKbTreeExpandedIfPersisted(nextPaths);
      return new Set(nextPaths);
    });
    setSessionReveal((prev) => {
      if (prev.size === 0) return prev;
      return new Set(resolveExpandedFolderPaths(tree, [...prev]));
    });
  }, [tree]);

  useEffect(() => {
    if (!didHydrateRef.current) return;
    if (hasPersistedExpanded()) {
      setSessionReveal((prev) => (prev.size === 0 ? prev : new Set()));
      return;
    }
    setSessionReveal(new Set(collectAncestorFolderPaths(activePaths)));
  }, [activePaths]);

  function toggleFolder(path: string) {
    const closing = expanded.has(path);
    setUserExpanded((prev) => {
      const next = new Set(prev);
      if (closing) next.delete(path);
      else next.add(path);
      saveKbTreeExpanded([...next]);
      return next;
    });
    if (closing) {
      setSessionReveal((prev) => {
        if (!prev.has(path)) return prev;
        const next = new Set(prev);
        next.delete(path);
        return next;
      });
    }
  }

  // —— 滚动：侧栏折叠时重置；展开就绪后恢复；用户滚动后落盘 ——
  useEffect(() => {
    if (collapsed) {
      phaseRef.current = "pending";
      allowPersistRef.current = false;
    }
  }, [collapsed]);

  useEffect(() => {
    if (collapsed || !scrollEnabled) return;
    const el = scrollRef.current;
    if (!el) return;

    let timer: ReturnType<typeof setTimeout> | undefined;
    const persist = () => {
      if (phaseRef.current !== "idle" || !allowPersistRef.current) return;
      saveKbTreeScrollTop(el.scrollTop);
    };
    const onScroll = () => {
      if (phaseRef.current !== "idle") return;
      allowPersistRef.current = true;
      if (timer) clearTimeout(timer);
      timer = setTimeout(persist, 120);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      if (timer) clearTimeout(timer);
      persist();
      el.removeEventListener("scroll", onScroll);
    };
  }, [collapsed, scrollEnabled, scrollRef]);

  useLayoutEffect(() => {
    if (collapsed || !hydrated || !scrollEnabled || phaseRef.current !== "pending") {
      return;
    }
    const el = scrollRef.current;
    if (!el) return;

    const storedTop = loadKbTreeUi()?.scrollTop;
    if (storedTop == null || storedTop <= 0) {
      phaseRef.current = "idle";
      return;
    }

    let cancelled = false;
    phaseRef.current = "restoring";
    allowPersistRef.current = false;
    const startedAt = performance.now();

    const finish = (top: number) => {
      if (cancelled || phaseRef.current !== "restoring") return;
      el.scrollTop = top;
      phaseRef.current = "idle";
    };

    const tryApply = (): boolean => {
      if (cancelled || phaseRef.current !== "restoring") return true;
      const maxScroll = Math.max(0, el.scrollHeight - el.clientHeight);
      if (maxScroll >= storedTop) {
        finish(storedTop);
        return true;
      }
      return false;
    };

    if (tryApply()) return;

    const ro =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => {
            if (tryApply()) ro?.disconnect();
          })
        : null;
    ro?.observe(el);

    const tick = () => {
      if (cancelled || phaseRef.current !== "restoring") {
        ro?.disconnect();
        return;
      }
      if (tryApply()) {
        ro?.disconnect();
        return;
      }
      if (performance.now() - startedAt >= RESTORE_TIMEOUT_MS) {
        finish(Math.max(0, el.scrollHeight - el.clientHeight));
        ro?.disconnect();
        return;
      }
      requestAnimationFrame(tick);
    };

    requestAnimationFrame(tick);
    return () => {
      cancelled = true;
      ro?.disconnect();
      if (phaseRef.current === "restoring") {
        phaseRef.current = "pending";
      }
    };
  }, [collapsed, hydrated, scrollEnabled, scrollRef]);

  return { tree, expanded, toggleFolder };
}
