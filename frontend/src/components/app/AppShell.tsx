import type { ComponentProps, ReactNode } from "react";
import { Sidebar } from "../Sidebar";

type Props = {
  panelFocus: boolean;
  floatFocus: boolean;
  hasMergeReview: boolean;
  mainFloatWide: boolean;
  sidebarProps: ComponentProps<typeof Sidebar>;
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
  sidebarProps,
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
      <Sidebar {...sidebarProps} />
      <main
        className={`main-panel${mainFloatWide ? " main-panel--float-wide" : ""}`}
      >
        {chat}
        {docFloat}
      </main>
      {docPinned}
      {modals}
    </div>
  );
}
