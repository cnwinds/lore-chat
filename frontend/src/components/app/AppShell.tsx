import type { ComponentProps, CSSProperties, ReactNode } from "react";
import { RoleList } from "../role/RoleList";
import { GroupList } from "../role/GroupList";
import { KbSidebar } from "../KbSidebar";
import { RoleConfigPanel } from "../role/RoleConfigPanel";
import { LeftSidebarFooter } from "./LeftSidebarFooter";
import { useLeftSidebarWidth } from "../../hooks/useLeftSidebarWidth";

type RoleListProps = ComponentProps<typeof RoleList>;
type GroupListProps = ComponentProps<typeof GroupList>;
type KbSidebarProps = ComponentProps<typeof KbSidebar>;
type RoleConfigPanelProps = ComponentProps<typeof RoleConfigPanel>;

type Props = {
  panelFocus: boolean;
  floatFocus: boolean;
  hasMergeReview: boolean;
  mainFloatWide: boolean;
  roleListProps: RoleListProps;
  groupListProps?: GroupListProps;
  kbSidebarProps: KbSidebarProps;
  roleConfigPanelProps: RoleConfigPanelProps;
  chat: ReactNode;
  docFloat: ReactNode | null;
  docPinned: ReactNode | null;
  modals: ReactNode;
  mobileLayout?: boolean;
  mobileNavOpen?: boolean;
  onMobileNavClose?: () => void;
  settingsAttention?: boolean;
  onOpenSettings?: () => void;
};

export function AppShell({
  panelFocus,
  floatFocus,
  hasMergeReview,
  mainFloatWide,
  roleListProps,
  groupListProps,
  kbSidebarProps,
  roleConfigPanelProps,
  chat,
  docFloat,
  docPinned,
  modals,
  mobileLayout = false,
  mobileNavOpen = false,
  onMobileNavClose,
  settingsAttention = false,
  onOpenSettings,
}: Props) {
  const leftSidebar = useLeftSidebarWidth();
  const shellClass = [
    "app-shell",
    "app-shell--three-pane",
    roleConfigPanelProps.collapsed ? "app-shell--config-collapsed" : "",
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
      <div
        className={`app-shell-left${leftSidebar.iconOnly ? " app-shell-left--icons" : ""}`}
      >
        <div className="app-shell-left-split" ref={leftSidebar.splitRef}>
          <RoleList {...roleListProps} />
          {groupListProps ? <GroupList {...groupListProps} /> : null}
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
      <RoleConfigPanel {...roleConfigPanelProps} />
      {docPinned}
      {modals}
    </div>
  );
}
