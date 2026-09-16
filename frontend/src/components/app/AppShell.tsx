import type { ComponentProps, CSSProperties, ReactNode } from "react";
import { RoleList } from "../role/RoleList";
import { KbSidebar } from "../KbSidebar";
import { RoleConfigPanel } from "../role/RoleConfigPanel";
import { GroupConfigPanel } from "../role/GroupConfigPanel";
import { LeftSidebarFooter } from "./LeftSidebarFooter";
import { useLeftSidebarWidth } from "../../hooks/useLeftSidebarWidth";
import { shouldUseLeftSidebarIcons } from "../../utils/leftSidebarWidth";

type RoleListProps = ComponentProps<typeof RoleList>;
type KbSidebarProps = ComponentProps<typeof KbSidebar>;
type RoleConfigPanelProps = ComponentProps<typeof RoleConfigPanel>;
type GroupConfigPanelProps = ComponentProps<typeof GroupConfigPanel>;

type Props = {
  panelFocus: boolean;
  floatFocus: boolean;
  hasMergeReview: boolean;
  mainFloatWide: boolean;
  configMode?: "role" | "group";
  roleListProps: RoleListProps;
  kbSidebarProps: KbSidebarProps;
  roleConfigPanelProps: RoleConfigPanelProps;
  groupConfigPanelProps?: GroupConfigPanelProps;
  chat: ReactNode;
  docFloat: ReactNode | null;
  docPinned: ReactNode | null;
  modals: ReactNode;
  mobileLayout?: boolean;
  mobileNavOpen?: boolean;
  onMobileNavClose?: () => void;
  settingsAttention?: boolean;
  onOpenSettings?: () => void;
  channelsOpen?: boolean;
  onToggleChannels?: () => void;
};

export function AppShell({
  panelFocus,
  floatFocus,
  hasMergeReview,
  mainFloatWide,
  configMode = "role",
  roleListProps,
  kbSidebarProps,
  roleConfigPanelProps,
  groupConfigPanelProps,
  chat,
  docFloat,
  docPinned,
  modals,
  mobileLayout = false,
  mobileNavOpen = false,
  onMobileNavClose,
  settingsAttention = false,
  onOpenSettings,
  channelsOpen = false,
  onToggleChannels,
}: Props) {
  const leftSidebar = useLeftSidebarWidth();
  const configCollapsed =
    configMode === "group"
      ? Boolean(groupConfigPanelProps?.collapsed)
      : Boolean(roleConfigPanelProps.collapsed);
  const onToggleConfig =
    configMode === "group"
      ? groupConfigPanelProps?.onToggleCollapsed
      : roleConfigPanelProps.onToggleCollapsed;
  const shellClass = [
    "app-shell",
    "app-shell--three-pane",
    configCollapsed ? "app-shell--config-collapsed" : "",
    panelFocus ? "app-shell--doc-focus" : "",
    floatFocus ? "app-shell--doc-focus-float" : "",
    docPinned ? "app-shell--doc-pinned" : "",
    mobileLayout ? "app-shell--mobile" : "",
    mobileLayout && mobileNavOpen ? "app-shell--mobile-nav-open" : "",
    leftSidebar.dragging ? "app-shell--left-resizing" : "",
    leftSidebar.splitDragging ? "app-shell--left-split-resizing" : "",
  ]
    .filter(Boolean)
    .join(" ");
  const leftStyle = {
    "--app-left-width": `${leftSidebar.width}px`,
    "--app-left-role-share": String(leftSidebar.roleShare),
  } as CSSProperties;

  return (
    <div
      className={shellClass}
      style={leftStyle}
      data-has-merge-review={hasMergeReview ? "1" : "0"}
    >
      {mobileLayout && mobileNavOpen && (
        <button
          type="button"
          className="app-mobile-nav-backdrop"
          aria-label="关闭导航"
          onClick={onMobileNavClose}
        />
      )}
      {mobileLayout && !configCollapsed && (
        <button
          type="button"
          className="app-mobile-config-backdrop"
          aria-label={configMode === "group" ? "关闭群设置" : "关闭角色设置"}
          onClick={onToggleConfig}
        />
      )}
      <div
        className={`app-shell-left${shouldUseLeftSidebarIcons(leftSidebar.width, mobileLayout) ? " app-shell-left--icons" : ""}`}
      >
        <div className="app-shell-left-split" ref={leftSidebar.splitRef}>
          <RoleList {...roleListProps} />
          {!mobileLayout && (
            <div
              className="app-shell-left-v-resizer"
              role="separator"
              aria-orientation="horizontal"
              aria-label="调整角色与知识库高度"
              onPointerDown={leftSidebar.onSplitPointerDown}
              onPointerMove={leftSidebar.onSplitPointerMove}
              onPointerUp={leftSidebar.onSplitPointerUp}
              onPointerCancel={leftSidebar.onSplitPointerUp}
            />
          )}
          <KbSidebar {...kbSidebarProps} />
        </div>
        <LeftSidebarFooter
          settingsAttention={settingsAttention}
          onOpenSettings={onOpenSettings}
          channelsOpen={channelsOpen}
          onToggleChannels={onToggleChannels}
        />
        {!mobileLayout && (
          <div
            className="app-shell-left-resizer"
            role="separator"
            aria-orientation="vertical"
            aria-label="调整侧栏宽度"
            onPointerDown={leftSidebar.onPointerDown}
            onPointerMove={leftSidebar.onPointerMove}
            onPointerUp={leftSidebar.onPointerUp}
            onPointerCancel={leftSidebar.onPointerUp}
          />
        )}
      </div>
      <main
        className={`main-panel${mainFloatWide ? " main-panel--float-wide" : ""}`}
      >
        {chat}
        {docFloat}
      </main>
      {configMode === "group" && groupConfigPanelProps ? (
        <GroupConfigPanel {...groupConfigPanelProps} />
      ) : (
        <RoleConfigPanel {...roleConfigPanelProps} />
      )}
      {docPinned}
      {modals}
    </div>
  );
}
