import { useEffect, useRef, useState } from "react";
import type { RoleSummary, RoomParticipant } from "../../api";
import { FoldChevron } from "../FoldChevron";
import { ChatRoleHeading } from "../chat/ChatRoleHeading";
import { GroupAvatar } from "../role/GroupAvatar";

type Props = {
  title: string;
  onOpenNav: () => void;
  onShare?: () => void;
  roles?: RoleSummary[];
  activeRoleId?: string | null;
  onSelectRole?: (id: string) => void;
  roomMode?: "role" | "group";
  roomAvatar?: string | null;
  roomParticipants?: RoomParticipant[];
  onToggleConfig?: () => void;
  configCollapsed?: boolean;
};

export function MobileChatHeader({
  title,
  onOpenNav,
  onShare,
  roles = [],
  activeRoleId = null,
  onSelectRole,
  roomMode = "role",
  roomAvatar = null,
  roomParticipants = [],
  onToggleConfig,
  configCollapsed = true,
}: Props) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const sheetRef = useRef<HTMLDivElement>(null);
  const multiRole = roomMode !== "group" && roles.length > 1 && !!onSelectRole;
  const activeRole = roles.find((r) => r.id === activeRoleId) ?? null;
  const headingName = roomMode === "group" ? title : activeRole?.name || title;
  const heading = (
    roomMode === "group" ? (
      <span className="chat-role-heading">
        <GroupAvatar
          name={headingName}
          seed={headingName}
          avatar={roomAvatar}
          members={roomParticipants}
          size={22}
        />
        <span className="chat-role-heading-name">{headingName}</span>
      </span>
    ) : (
      <ChatRoleHeading
        name={headingName}
        roleId={activeRole?.id || activeRoleId}
        avatar={activeRole?.avatar}
      />
    )
  );

  useEffect(() => {
    if (!sheetOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setSheetOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [sheetOpen]);

  return (
    <header className="mobile-chat-header">
      <button
        type="button"
        className="mobile-chat-header-btn"
        onClick={onOpenNav}
        aria-label="打开导航"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
          <path
            d="M4 7h16M4 12h16M4 17h16"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      </button>
      {multiRole ? (
        <button
          type="button"
          className="mobile-chat-header-title mobile-chat-header-title--btn"
          onClick={() => setSheetOpen(true)}
          aria-haspopup="dialog"
          aria-expanded={sheetOpen}
        >
          {heading}
          <FoldChevron
            open={sheetOpen}
            from="down"
            className="mobile-chat-header-caret"
          />
        </button>
      ) : (
        <h1 className="mobile-chat-header-title">
          {heading}
        </h1>
      )}
      <div className="mobile-chat-header-actions">
        {onToggleConfig ? (
          <button
            type="button"
            className="mobile-chat-header-btn"
            onClick={onToggleConfig}
            aria-label={
              roomMode === "group"
                ? configCollapsed
                  ? "展开群设置"
                  : "收起群设置"
                : configCollapsed
                  ? "展开角色设置"
                  : "收起角色设置"
            }
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
              <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.8" />
              <path
                d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9c.3.7 1 1.2 1.8 1.2H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        ) : null}
        {onShare && (
          <button
            type="button"
            className="mobile-chat-header-btn"
            onClick={onShare}
            aria-label="分享对话"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path
                d="M12 3v10M8 7l4-4 4 4M5 21h14a2 2 0 0 0 2-2v-5"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        )}
      </div>
      {sheetOpen && multiRole && (
        <div
          className="mobile-role-sheet-backdrop"
          onClick={() => setSheetOpen(false)}
        >
          <div
            ref={sheetRef}
            className="mobile-role-sheet"
            role="dialog"
            aria-label="切换角色"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mobile-role-sheet-title">切换角色</div>
            <div className="mobile-role-sheet-list">
              {roles.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  className={`mobile-role-sheet-item${
                    activeRoleId === r.id ? " active" : ""
                  }`}
                  onClick={() => {
                    onSelectRole?.(r.id);
                    setSheetOpen(false);
                  }}
                >
                  {r.name}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
