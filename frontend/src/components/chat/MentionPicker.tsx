import { useEffect, useRef } from "react";
import type { MentionCandidate } from "../../utils/roleMentions";
import { RoleAvatar } from "../role/RoleAvatar";
import { MENTION_PICKER_ID, mentionOptionId } from "./mentionPickerIds";

type Props = {
  roles: MentionCandidate[];
  query: string;
  selectedIndex: number;
  onHover: (index: number) => void;
  onPick: (role: MentionCandidate) => void;
};

function highlightQuery(text: string, query: string) {
  const needle = query.trim();
  if (!needle) return text;
  const idx = text.toLowerCase().indexOf(needle.toLowerCase());
  if (idx < 0) return text;
  return (
    <>
      {text.slice(0, idx)}
      <mark>{text.slice(idx, idx + needle.length)}</mark>
      {text.slice(idx + needle.length)}
    </>
  );
}

export function MentionPicker({
  roles,
  query,
  selectedIndex,
  onHover,
  onPick,
}: Props) {
  const activeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    activeRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [selectedIndex, roles]);

  const hint = query.trim()
    ? `筛选 · ${query}`
    : roles.length
      ? "↑↓ 选择 · Enter 点名"
      : "没有可点名的成员";

  return (
    <div
      id={MENTION_PICKER_ID}
      className="mention-picker"
      role="listbox"
      aria-label="点名成员"
    >
      <div className="mention-picker-head">
        <span>成员</span>
        <span className="mention-picker-hint">{hint}</span>
      </div>
      {roles.length === 0 ? (
        <div className="mention-picker-empty">没有叫这个名字的成员</div>
      ) : (
        <div className="mention-picker-list">
          {roles.map((role, index) => {
            const active = index === selectedIndex;
            return (
              <button
                key={role.id}
                id={mentionOptionId(role.id)}
                ref={active ? activeRef : undefined}
                type="button"
                role="option"
                aria-selected={active}
                className={`mention-picker-item${active ? " is-active" : ""}`}
                onMouseEnter={() => onHover(index)}
                onMouseDown={(e) => {
                  e.preventDefault();
                  onPick(role);
                }}
              >
                <RoleAvatar
                  name={role.name}
                  seed={role.id}
                  avatar={role.avatar}
                  size={28}
                />
                <span className="mention-picker-item-name">
                  {highlightQuery(role.name, query)}
                </span>
                <span className="mention-picker-item-insert" aria-hidden>
                  @{role.name}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
