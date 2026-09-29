import { useRef, useState, type ReactNode } from "react";
import { FixedOverflowMenu } from "../FixedOverflowMenu";
import { DocIconBtn, MoreIcon } from "../DocToolbarIcons";

export type MemoryFactMenuAction = {
  id: string;
  label: string;
  icon: ReactNode;
  danger?: boolean;
  onClick: () => void;
};

export function MemoryFactMenu({
  actions,
  disabled,
  label = "记忆操作",
}: {
  actions: MemoryFactMenuAction[];
  disabled?: boolean;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  if (actions.length === 0) return null;

  return (
    <div ref={rootRef} className="doc-overflow-anchor">
      <DocIconBtn
        label="更多操作"
        className="memory-fact-icon-btn"
        disabled={disabled}
        active={open}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <MoreIcon />
      </DocIconBtn>
      <FixedOverflowMenu
        open={open}
        anchorRef={rootRef}
        align="end"
        label={label}
        onDismiss={() => setOpen(false)}
      >
        {actions.map((action) => (
          <button
            key={action.id}
            type="button"
            role="menuitem"
            className={`doc-overflow-item${action.danger ? " doc-overflow-item--danger" : ""}`}
            disabled={disabled}
            title={action.label}
            onClick={() => {
              action.onClick();
              setOpen(false);
            }}
          >
            {action.icon}
            <span>{action.label}</span>
          </button>
        ))}
      </FixedOverflowMenu>
    </div>
  );
}

export function MemoryStatement({
  statement,
  conversationIds,
  disabled,
  onOpenConversation,
}: {
  statement: string;
  conversationIds: string[];
  disabled?: boolean;
  onOpenConversation?: (conversationId: string) => void;
}) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const canJump =
    Boolean(onOpenConversation) && conversationIds.length > 0 && !disabled;
  const multi = conversationIds.length > 1;

  if (!canJump) {
    return <p className="memory-fact-statement">{statement}</p>;
  }

  function openOne(cid: string) {
    onOpenConversation?.(cid);
    setPickerOpen(false);
  }

  return (
    <div ref={rootRef} className="memory-fact-statement-anchor">
      <button
        type="button"
        className="memory-fact-statement memory-fact-statement--jump"
        title={multi ? "选择来源会话" : "打开来源会话"}
        aria-label={multi ? "选择来源会话" : "打开来源会话"}
        aria-expanded={multi ? pickerOpen : undefined}
        aria-haspopup={multi ? "menu" : undefined}
        onClick={() => {
          if (!multi) {
            openOne(conversationIds[0]);
            return;
          }
          setPickerOpen((v) => !v);
        }}
      >
        {statement}
      </button>
      {multi ? (
        <FixedOverflowMenu
          open={pickerOpen}
          anchorRef={rootRef}
          align="start"
          label="来源会话"
          onDismiss={() => setPickerOpen(false)}
        >
          {conversationIds.map((cid) => (
            <button
              key={cid}
              type="button"
              role="menuitem"
              className="doc-overflow-item"
              title={cid}
              aria-label={`打开来源会话 ${cid}`}
              onClick={() => openOne(cid)}
            >
              会话 {cid.length > 8 ? `${cid.slice(0, 8)}…` : cid}
            </button>
          ))}
        </FixedOverflowMenu>
      ) : null}
    </div>
  );
}
