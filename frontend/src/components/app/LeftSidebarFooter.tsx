import { ThemeToggle } from "../ThemeToggle";
import { SettingsAttentionDot } from "../settings/SettingsAttentionDot";

type Props = {
  settingsAttention?: boolean;
  onOpenSettings?: () => void;
};

export function LeftSidebarFooter({
  settingsAttention = false,
  onOpenSettings,
}: Props) {
  return (
    <footer className="sidebar-footer">
      <div className="sidebar-footer-actions">
        <ThemeToggle />
        {onOpenSettings ? (
          <button
            type="button"
            className="sidebar-settings-btn"
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
