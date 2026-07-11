import { useEffect, useRef } from "react";
import type { OutlineItem } from "../utils/docOutline";
import { DocIconBtn, OutlineIcon } from "./DocToolbarIcons";

type Props = {
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
  items: OutlineItem[];
  activeIndex?: number;
  onJump: (item: OutlineItem) => void;
  disabled?: boolean;
};

export function DocOutlineMenu({
  open,
  onToggle,
  onClose,
  items,
  activeIndex = -1,
  onJump,
  disabled = false,
}: Props) {
  const rootRef = useRef<HTMLDivElement>(null);
  const activeItemRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    }
    function onPointerDown(e: MouseEvent) {
      const root = rootRef.current;
      if (root && !root.contains(e.target as Node)) {
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown, true);
    window.addEventListener("mousedown", onPointerDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown, true);
      window.removeEventListener("mousedown", onPointerDown);
    };
  }, [open, onClose]);

  useEffect(() => {
    if (!open || activeIndex < 0) return;
    activeItemRef.current?.scrollIntoView({ block: "nearest" });
  }, [open, activeIndex]);

  const handleJump = (item: OutlineItem) => {
    onJump(item);
    onClose();
  };

  return (
    <div ref={rootRef} className="doc-outline-anchor">
      <DocIconBtn
        className={`doc-outline-toggle${open ? " is-open" : ""}`}
        label={`文档目录${items.length > 0 ? `（${items.length} 个标题）` : ""}`}
        active={open}
        onClick={onToggle}
        disabled={disabled}
        aria-expanded={open}
        aria-haspopup="true"
      >
        <OutlineIcon />
        {items.length > 0 && (
          <span className="doc-outline-toggle-badge" aria-hidden>
            {items.length}
          </span>
        )}
      </DocIconBtn>
      {open && (
        <div className="doc-outline-dropdown" role="menu" aria-label="文档目录">
          {items.length === 0 ? (
            <p className="doc-outline-empty">暂无标题（使用 # 标题）</p>
          ) : (
            <nav className="doc-outline-list">
              {items.map((item) => {
                const isActive = item.index === activeIndex;
                return (
                <button
                  key={item.id}
                  ref={isActive ? activeItemRef : undefined}
                  type="button"
                  role="menuitem"
                  className={`doc-outline-item${isActive ? " is-active" : ""}`}
                  style={{ paddingLeft: `${10 + (item.level - 1) * 12}px` }}
                  title={item.text}
                  aria-current={isActive ? "location" : undefined}
                  onClick={() => handleJump(item)}
                >
                  <span className="doc-outline-item-level" aria-hidden>
                    H{item.level}
                  </span>
                  <span className="doc-outline-item-text">{item.text}</span>
                </button>
                );
              })}
            </nav>
          )}
        </div>
      )}
    </div>
  );
}
