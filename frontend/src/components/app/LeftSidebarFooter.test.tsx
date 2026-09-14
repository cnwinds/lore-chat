import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LeftSidebarFooter } from "./LeftSidebarFooter";

afterEach(() => {
  cleanup();
});

describe("LeftSidebarFooter", () => {
  it("keeps the light dock with 聊天通道 and 设置", () => {
    const onToggleChannels = vi.fn();
    const onOpenSettings = vi.fn();
    render(
      <LeftSidebarFooter
        channelsOpen
        onToggleChannels={onToggleChannels}
        onOpenSettings={onOpenSettings}
      />,
    );
    expect(screen.getByRole("button", { name: "聊天通道" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "设置" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/切换为/)).toBeNull();
  });
});
