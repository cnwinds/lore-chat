import { useEffect, useState } from "react";

const HOVER_QUERY = "(hover: hover) and (pointer: fine)";

/** 是否具备稳定悬停（桌面鼠标）；触摸/窄指针为 false。 */
export function useHoverCapable(): boolean {
  const [capable, setCapable] = useState(() => {
    if (typeof window === "undefined" || !window.matchMedia) return true;
    return window.matchMedia(HOVER_QUERY).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia(HOVER_QUERY);
    const onChange = () => setCapable(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return capable;
}
