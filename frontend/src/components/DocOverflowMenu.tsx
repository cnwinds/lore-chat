import { useEffect, useRef, useState } from "react";
import { ChatIcon, DiffIcon, DocIconBtn, EditIcon, MoreIcon } from "./DocToolbarIcons";

export type OverflowItem =
  | {
      id: string;
      label: string;
      icon: "edit" | "chat" | "diff";
      active?: boolean;
      onClick: () => void;
    };

type Props = {
  items: OverflowItem[];
  disabled?: boolean;
};

function ItemIcon({ type }: { type: "edit" | "chat" | "diff" }) {
  if (type === "diff") return <DiffIcon size={14} />;
  return type === "edit" ? <EditIcon size={14} /> : <ChatIcon size={14} />;
}

export function DocOverflowMenu({ items, disabled = false }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
      }
    }
    function onPointerDown(e: MouseEvent) {
      const root = rootRef.current;
      if (root && !root.contains(e.target as Node)) setOpen(false);
    }
    window.addEventListener("keydown", onKeyDown, true);
    window.addEventListener("mousedown", onPointerDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown, true);
      window.removeEventListener("mousedown", onPointerDown);
    };
  }, [open]);

  if (items.length === 0) return null;

  return (
    <div ref={rootRef} className="doc-overflow-anchor">
      <DocIconBtn
        label="更多操作"
        active={open}
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <MoreIcon />
      </DocIconBtn>
      {open && (
        <div className="doc-overflow-menu" role="menu">
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              role="menuitem"
              className={`doc-overflow-item${item.active ? " is-active" : ""}`}
              onClick={() => {
                item.onClick();
                setOpen(false);
              }}
            >
              <ItemIcon type={item.icon} />
              <span>{item.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
