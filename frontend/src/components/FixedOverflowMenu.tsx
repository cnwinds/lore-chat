import {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";
import { useDismissOnOutsideClick } from "../hooks/useDismissOnOutsideClick";
import { anchoredMenuBox } from "../utils/anchoredMenuBox";

type Props = {
  open: boolean;
  anchorRef: RefObject<HTMLElement | null>;
  align?: "start" | "end";
  label?: string;
  className?: string;
  /** 默认 menu；内嵌 listbox 等时用 presentation 避免嵌套语义冲突。 */
  containerRole?: "menu" | "presentation";
  onDismiss: () => void;
  children: ReactNode;
};

/** 溢出菜单挂到 body，避免被滚动容器 / 浮窗顶栏裁切。 */
export function FixedOverflowMenu({
  open,
  anchorRef,
  align = "end",
  label,
  className,
  containerRole = "menu",
  onDismiss,
  children,
}: Props) {
  const menuRef = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<{ top: number; left: number } | null>(null);

  const update = useCallback(() => {
    const anchor = anchorRef.current;
    const menu = menuRef.current;
    if (!anchor || !menu) return;
    setBox(
      anchoredMenuBox(
        anchor.getBoundingClientRect(),
        { width: menu.offsetWidth, height: menu.offsetHeight },
        { width: window.innerWidth, height: window.innerHeight },
        { align },
      ),
    );
  }, [align, anchorRef]);

  useLayoutEffect(() => {
    if (!open) {
      setBox(null);
      return;
    }
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [open, update, children]);

  useDismissOnOutsideClick([anchorRef, menuRef], open, onDismiss, {
    escape: true,
    pointerEvent: "mousedown",
  });

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      ref={menuRef}
      className={`doc-overflow-menu doc-overflow-menu--fixed${className ? ` ${className}` : ""}`}
      role={containerRole}
      aria-label={containerRole === "menu" ? label : undefined}
      style={
        box
          ? { top: box.top, left: box.left }
          : { top: 0, left: 0, visibility: "hidden" }
      }
    >
      {children}
    </div>,
    document.body,
  );
}
