import { useEffect, useState } from "react";

/** 主应用手机布局断点（侧栏抽屉、全屏文档等）。 */
export const APP_MOBILE_QUERY = "(max-width: 768px)";

export function useMobileLayout(): boolean {
  const [mobile, setMobile] = useState(() => {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia(APP_MOBILE_QUERY).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia(APP_MOBILE_QUERY);
    const onChange = () => setMobile(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return mobile;
}
