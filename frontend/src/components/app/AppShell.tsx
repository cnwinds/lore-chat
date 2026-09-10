import type { ComponentProps, ReactNode } from "react";
import { RoleList } from "../role/RoleList";
import { KbSidebar } from "../KbSidebar";
import { RoleConfigPanel } from "../role/RoleConfigPanel";

type RoleListProps = ComponentProps<typeof RoleList>;
type KbSidebarProps = ComponentProps<typeof KbSidebar>;
type RoleConfigPanelProps = ComponentProps<typeof RoleConfigPanel>;

type Props = {
  panelFocus: boolean;
  floatFocus: boolean;
  hasMergeReview: boolean;
  mainFloatWide: boolean;
  roleListProps: RoleListProps;
  kbSidebarProps: KbSidebarProps;
  roleConfigPanelProps: RoleConfigPanelProps;
  chat: ReactNode;
  docFloat: ReactNode | null;
  docPinned: ReactNode | null;
  modals: ReactNode;
  mobileLayout?: boolean;
  mobileNavOpen?: boolean;
  onMobileNavClose?: () => void;
};

export function AppShell({
  panelFocus,
  floatFocus,
  hasMergeReview,
  mainFloatWide,
  roleListProps,
  kbSidebarProps,
  roleConfigPanelProps,
  chat,
  docFloat,
  docPinned,
  modals,
  mobileLayout = false,
  mobileNavOpen = false,
  onMobileNavClose,
}: Props) {
  const shellClass = [
    "app-shell",
    "app-shell--three-pane",
    panelFocus ? "app-shell--doc-focus" : "",
    floatFocus ? "app-shell--doc-focus-float" : "",
    mobileLayout ? "app-shell--mobile" : "",
    mobileLayout && mobileNavOpen ? "app-shell--mobile-nav-open" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={shellClass} data-has-merge-review={hasMergeReview ? "1" : "0"}>
      {mobileLayout && mobileNavOpen && (
        <button
          type="button"
          className="app-mobile-nav-backdrop"
          aria-label="关闭导航"
          onClick={onMobileNavClose}
        />
      )}
      <div className="app-shell-left">
        <RoleList {...roleListProps} />
        <KbSidebar {...kbSidebarProps} />
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
