import { useEffect, useRef, useState } from "react";
import { DocIconBtn, InfoIcon } from "./DocToolbarIcons";

type Props = {
  meta: Record<string, unknown>;
};

export function DocMetaPopover({ meta }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const entries = Object.entries(meta).filter(([k]) => k !== "conversation_id");

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

  if (entries.length === 0) return null;

  return (
    <div ref={rootRef} className="doc-meta-anchor">
      <DocIconBtn
        label="文档信息"
        active={open}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="dialog"
      >
        <InfoIcon />
      </DocIconBtn>
      {open && (
        <div className="doc-meta-popover" role="dialog" aria-label="文档信息">
          <dl className="doc-meta-list">
            {entries.map(([k, v]) => (
              <div key={k} className="doc-meta-row">
                <dt>{k}</dt>
                <dd>{Array.isArray(v) ? v.join(", ") : String(v)}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}
