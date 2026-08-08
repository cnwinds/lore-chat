import { useRef, useState } from "react";
import { useDismissOnOutsideClick } from "../hooks/useDismissOnOutsideClick";
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

  useDismissOnOutsideClick(rootRef, open, () => setOpen(false), {
    escape: true,
    pointerEvent: "mousedown",
  });

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
