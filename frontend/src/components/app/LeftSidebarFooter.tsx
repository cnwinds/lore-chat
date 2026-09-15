import { SettingsAttentionDot } from "../settings/SettingsAttentionDot";
import { ThemeToggle } from "../ThemeToggle";

type Props = {
  settingsAttention?: boolean;
  channelsOpen?: boolean;
  onOpenSettings?: () => void;
  onToggleChannels?: () => void;
};

export function LeftSidebarFooter({
  settingsAttention = false,
  channelsOpen = false,
  onOpenSettings,
  onToggleChannels,
}: Props) {
  return (
    <footer className="sidebar-footer">
      <div className="sidebar-footer-actions">
        <ThemeToggle compact />
        {onToggleChannels ? (
          <button
            type="button"
            className={`sidebar-dock-btn${channelsOpen ? " sidebar-dock-btn--active" : ""}`}
            onClick={onToggleChannels}
            aria-pressed={channelsOpen}
            data-channel-dock=""
            title="聊天通道"
          >
            <span className="sidebar-dock-icon" aria-hidden>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                <path
                  d="M5 7h14M5 12h14M5 17h9"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                />
              </svg>
            </span>
            <span className="sidebar-settings-label">聊天通道</span>
          </button>
        ) : null}
        {onOpenSettings ? (
          <button
            type="button"
            className="sidebar-dock-btn sidebar-settings-btn"
            onClick={onOpenSettings}
            title={
              settingsAttention
                ? "系统设置（有待办）"
                : "系统设置"
            }
          >
            <span className="sidebar-settings-icon" aria-hidden>
              ⚙
            </span>
            <span className="sidebar-settings-label">
              设置
              {settingsAttention ? (
                <SettingsAttentionDot title="有待办" />
              ) : null}
            </span>
          </button>
        ) : null}
      </div>
    </footer>
  );
}
