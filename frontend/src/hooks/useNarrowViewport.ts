import { useEffect, useState } from "react";

/** 与分享页移动端布局断点一致（含小平板，避免顶栏目录条）。 */
export const SHARE_NARROW_QUERY = "(max-width: 860px)";

/** 窄视口：分享页改用 FAB + 底部抽屉。 */
export function useNarrowViewport(): boolean {
  const [narrow, setNarrow] = useState(() => {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia(SHARE_NARROW_QUERY).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia(SHARE_NARROW_QUERY);
    const onChange = () => setNarrow(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return narrow;
}
