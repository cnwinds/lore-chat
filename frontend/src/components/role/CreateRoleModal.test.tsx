import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CreateRoleModal } from "./CreateRoleModal";

afterEach(() => {
  cleanup();
});

describe("CreateRoleModal", () => {
  it("renders a surfaced dialog on the dimmed backdrop", () => {
    render(
      <CreateRoleModal open onClose={vi.fn()} onConfirm={vi.fn()} />,
    );
    expect(document.querySelector(".modal-backdrop")).toBeTruthy();
    const dialog = screen.getByRole("dialog", { name: "创建新角色" });
    expect(dialog).toHaveClass("modal-panel");
    expect(dialog).toHaveClass("role-settings-modal");
    expect(screen.getByPlaceholderText("例如：股票研究员")).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    render(
      <CreateRoleModal open={false} onClose={vi.fn()} onConfirm={vi.fn()} />,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("submits name and avatar", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <CreateRoleModal open onClose={vi.fn()} onConfirm={onConfirm} />,
    );
    await user.type(screen.getByPlaceholderText("例如：股票研究员"), "研究员");
    await user.type(
      screen.getByPlaceholderText("媒体/…png 或 https://…"),
      "媒体/a.png",
    );
    await user.click(screen.getByRole("button", { name: "创建" }));
    expect(onConfirm).toHaveBeenCalledWith("研究员", "媒体/a.png");
  });

  it("closes when the backdrop is clicked", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <CreateRoleModal open onClose={onClose} onConfirm={vi.fn()} />,
    );
    await user.click(document.querySelector(".modal-backdrop")!);
    expect(onClose).toHaveBeenCalled();
  });
});
