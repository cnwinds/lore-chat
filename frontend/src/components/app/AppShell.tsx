import type { ComponentProps, ReactNode } from "react";
import { Sidebar } from "../Sidebar";
import { DemoBanner } from "../demo/DemoBanner";
import { DemoTour } from "../demo/DemoTour";

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
}: Props) {
  return (
    <div
      className={`app-shell${panelFocus ? " app-shell--doc-focus" : ""}${
        floatFocus ? " app-shell--doc-focus-float" : ""
      }`}
      data-has-merge-review={hasMergeReview ? "1" : "0"}
    >
      <DemoBanner />
      <DemoTour />
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
