import { useRef, useState } from "react";
import type { RequestCallSummary } from "../../../api";
import { FixedOverflowMenu } from "../../FixedOverflowMenu";

type Props = {
  calls: RequestCallSummary[];
  resolvedId: number | null;
  labelFor: (c: RequestCallSummary) => string;
  onSelect: (id: number) => void;
};

/** 请求快照选择：自定义列表，避免原生 select 弹出层与主题配色不一致。 */
export function RequestInspectorCallPicker({
  calls,
  resolvedId,
  labelFor,
  onSelect,
}: Props) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const current = calls.find((c) => c.id === resolvedId);

  return (
    <div className="reqinspector-call-select-wrap">
      <button
        ref={triggerRef}
        type="button"
        className="reqinspector-call-trigger"
        disabled={calls.length === 0}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="请求快照"
        title={current ? labelFor(current) : "请求快照"}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="reqinspector-call-trigger-label">
          {current ? labelFor(current) : "—"}
        </span>
        <span className="reqinspector-call-trigger-chevron" aria-hidden />
      </button>
      <FixedOverflowMenu
        open={open}
        anchorRef={triggerRef}
        align="start"
        label="请求快照"
        containerRole="presentation"
        className="reqinspector-call-menu-panel"
        onDismiss={() => setOpen(false)}
      >
        <ul className="reqinspector-call-menu" role="listbox" aria-label="请求快照">
          {calls.map((c) => {
            const selected = c.id === resolvedId;
            return (
              <li key={c.id} role="none">
                <button
                  type="button"
                  role="option"
                  aria-selected={selected}
                  className={`reqinspector-call-menu-item${selected ? " is-selected" : ""}`}
                  onClick={() => {
                    onSelect(c.id);
                    setOpen(false);
                  }}
                >
                  {labelFor(c)}
                </button>
              </li>
            );
          })}
        </ul>
      </FixedOverflowMenu>
    </div>
  );
}
