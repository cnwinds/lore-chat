import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { DocViewerHeader } from "./DocViewerHeader";
import type { EditMode } from "../../types/doc";

const baseProps = {
  mode: "float" as const,
  path: "系统/戒律.md",
  doc: { rel_path: "系统/戒律.md", meta: { title: "戒律" }, body: "" },
  dirty: false,
  onClose: () => undefined,
  loading: false,
  mergeEditing: false,
  readOnly: false,
  saving: false,
  mergeReview: null,
  onDiscard: () => undefined,
  onSave: () => undefined,
  onMergeSave: () => undefined,
  onViewDiff: () => undefined,
  outlineOpen: false,
  onOutlineToggle: () => undefined,
  onOutlineClose: () => undefined,
  outlineItems: [],
  outlineActiveIndex: -1,
  onOutlineJump: () => undefined,
  docWidth: "wide" as const,
  docFocus: false,
  onToggleWidth: () => undefined,
  onToggleFocus: () => undefined,
  onMergeEditingToggle: () => undefined,
  onShareDoc: () => undefined,
};

describe("DocViewerHeader", () => {
  afterEach(() => {
    cleanup();
  });

  it("shows an icon-only revision button", () => {
    const onViewHistory = vi.fn();
    render(
      <DocViewerHeader
        {...baseProps}
        editMode="preview"
        onEditModeChange={() => undefined}
        onViewHistory={onViewHistory}
      />,
    );
    const history = screen.getByRole("button", { name: "修订" });
    fireEvent.click(history);
    expect(onViewHistory).toHaveBeenCalled();
    expect(history.textContent?.trim()).toBe("");
    fireEvent.click(screen.getByRole("button", { name: "更多操作" }));
    expect(screen.queryByRole("menuitem", { name: "修订" })).toBeNull();
    expect(screen.getByRole("menuitem", { name: "分享" })).toBeInTheDocument();
    const inspect = screen.getByRole("group", { name: "文档查阅" });
    expect(inspect).toContainElement(
      screen.getByRole("button", { name: "文档信息" }),
    );
    expect(inspect).toContainElement(
      screen.getByRole("button", { name: "文档目录" }),
    );
    const reading = screen.getByRole("group", { name: "阅读版式" });
    expect(reading).toHaveClass("doc-toolbar-wide-only");
    expect(reading).toContainElement(screen.getByRole("button", { name: "宽" }));
    expect(reading).toContainElement(
      screen.getByRole("button", { name: "沉静阅读" }),
    );
    expect(screen.getByRole("button", { name: "宽" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.queryByRole("button", { name: "收窄阅读区" })).toBeNull();
    expect(screen.queryByRole("button", { name: "专注阅读" })).toBeNull();
    expect(screen.queryByRole("button", { name: "沉浸阅读" })).toBeNull();
  });

  it("switches wide and quiet reading as one control", () => {
    const onToggleWidth = vi.fn();
    const onToggleFocus = vi.fn();
    const { rerender } = render(
      <DocViewerHeader
        {...baseProps}
        editMode="preview"
        onEditModeChange={() => undefined}
        onViewHistory={() => undefined}
        onToggleWidth={onToggleWidth}
        onToggleFocus={onToggleFocus}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "沉静阅读" }));
    expect(onToggleFocus).toHaveBeenCalledTimes(1);
    expect(onToggleWidth).not.toHaveBeenCalled();

    rerender(
      <DocViewerHeader
        {...baseProps}
        editMode="preview"
        onEditModeChange={() => undefined}
        onViewHistory={() => undefined}
        docFocus
        onToggleWidth={onToggleWidth}
        onToggleFocus={onToggleFocus}
      />,
    );
    expect(screen.getByRole("button", { name: "沉静阅读" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: "宽" }));
    expect(onToggleFocus).toHaveBeenCalledTimes(2);

    rerender(
      <DocViewerHeader
        {...baseProps}
        editMode="preview"
        onEditModeChange={() => undefined}
        onViewHistory={() => undefined}
        docWidth="narrow"
        onToggleWidth={onToggleWidth}
        onToggleFocus={onToggleFocus}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "宽" }));
    expect(onToggleWidth).toHaveBeenCalledTimes(1);
  });

  it("toggles preview and source with one development button", () => {
    const onEditModeChange = vi.fn<(mode: EditMode) => void>();
    const { rerender } = render(
      <DocViewerHeader
        {...baseProps}
        editMode="preview"
        onEditModeChange={onEditModeChange}
        onViewHistory={() => undefined}
      />,
    );
    expect(screen.queryByRole("button", { name: "预览模式" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Markdown 源码" })).toBeNull();
    const enter = screen.getByRole("button", { name: "开发" });
    expect(enter.textContent?.trim()).toBe("");
    fireEvent.click(enter);
    expect(onEditModeChange).toHaveBeenCalledWith("markdown");

    rerender(
      <DocViewerHeader
        {...baseProps}
        editMode="markdown"
        onEditModeChange={onEditModeChange}
        onViewHistory={() => undefined}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "退出开发" }));
    expect(onEditModeChange).toHaveBeenCalledWith("preview");
  });
});
