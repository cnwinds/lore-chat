import { useEffect, useRef, useState } from "react";
import type { RoleSummary } from "../../api";
import { ChatRoleHeading } from "../chat/ChatRoleHeading";

type Props = {
  title: string;
  onOpenNav: () => void;
  onShare?: () => void;
  roles?: RoleSummary[];
  activeRoleId?: string | null;
  onSelectRole?: (id: string) => void;
};

export function MobileChatHeader({
  title,
  onOpenNav,
  onShare,
  roles = [],
  activeRoleId = null,
  onSelectRole,
}: Props) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const sheetRef = useRef<HTMLDivElement>(null);
  const multiRole = roles.length > 1 && !!onSelectRole;
  const activeRole = roles.find((r) => r.id === activeRoleId) ?? null;
  const headingName = activeRole?.name || title;

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
          <ChatRoleHeading
            name={headingName}
            roleId={activeRole?.id || activeRoleId}
            avatar={activeRole?.avatar}
          />
          <span className="mobile-chat-header-caret" aria-hidden>
            ▾
          </span>
        </button>
      ) : (
        <h1 className="mobile-chat-header-title">
          <ChatRoleHeading
            name={headingName}
            roleId={activeRole?.id || activeRoleId}
            avatar={activeRole?.avatar}
          />
        </h1>
      )}
      <div className="mobile-chat-header-actions">
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
