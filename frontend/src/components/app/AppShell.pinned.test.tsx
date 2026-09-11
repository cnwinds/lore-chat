import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "./AppShell";

afterEach(() => {
  cleanup();
});

vi.mock("../role/RoleList", () => ({
  RoleList: () => <div data-testid="role-list" />,
}));
vi.mock("../KbSidebar", () => ({
  KbSidebar: () => <div data-testid="kb-sidebar" />,
}));
vi.mock("../role/RoleConfigPanel", () => ({
  RoleConfigPanel: ({ collapsed }: { collapsed?: boolean }) => (
    <aside
      className={`role-config-panel${collapsed ? " role-config-panel--collapsed" : ""}`}
    />
  ),
}));
vi.mock("./LeftSidebarFooter", () => ({
  LeftSidebarFooter: () => <footer data-testid="left-footer" />,
}));

const roleListProps = {} as never;
const kbSidebarProps = {} as never;

describe("AppShell pinned document class", () => {
  it("marks the shell when a document is pinned to the right column", () => {
    const { container, rerender } = render(
      <AppShell
        panelFocus={false}
        floatFocus={false}
        hasMergeReview={false}
        mainFloatWide={false}
        roleListProps={roleListProps}
        kbSidebarProps={kbSidebarProps}
        roleConfigPanelProps={{ roleId: "default", collapsed: true }}
        chat={<div>chat</div>}
        docFloat={null}
        docPinned={null}
        modals={null}
      />,
    );

    expect(container.firstElementChild?.className).not.toContain(
      "app-shell--doc-pinned",
    );

    rerender(
      <AppShell
        panelFocus={false}
        floatFocus={false}
        hasMergeReview={false}
        mainFloatWide={false}
        roleListProps={roleListProps}
        kbSidebarProps={kbSidebarProps}
        roleConfigPanelProps={{ roleId: "default", collapsed: true }}
        chat={<div>chat</div>}
        docFloat={null}
        docPinned={<aside className="doc-panel">doc</aside>}
        modals={null}
      />,
    );

    expect(container.firstElementChild?.className).toContain(
      "app-shell--doc-pinned",
    );
  });
});
