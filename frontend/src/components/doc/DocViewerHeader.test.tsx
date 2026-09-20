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
    const share = screen.getByRole("button", { name: "分享" });
    expect(share.textContent?.trim()).toBe("");
    expect(screen.queryByRole("button", { name: "更多操作" })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: "分享" })).toBeNull();
    const inspect = screen.getByRole("group", { name: "文档查阅" });
    expect(inspect).toContainElement(
      screen.getByRole("button", { name: "文档信息" }),
    );
    expect(inspect).toContainElement(
      screen.getByRole("button", { name: "文档目录" }),
    );
    const quiet = screen.getByRole("button", { name: "沉静阅读" });
    expect(quiet).toHaveClass("doc-toolbar-wide-only");
    expect(quiet.textContent?.trim()).toBe("");
    expect(quiet).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByRole("group", { name: "阅读版式" })).toBeNull();
    expect(screen.queryByRole("button", { name: "宽" })).toBeNull();
    expect(screen.queryByRole("button", { name: "收窄阅读区" })).toBeNull();
    expect(screen.queryByRole("button", { name: "专注阅读" })).toBeNull();
    expect(screen.queryByRole("button", { name: "沉浸阅读" })).toBeNull();
  });

  it("toggles quiet reading as one switch", () => {
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
    const quiet = screen.getByRole("button", { name: "沉静阅读" });
    fireEvent.click(quiet);
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
    fireEvent.click(screen.getByRole("button", { name: "沉静阅读" }));
    expect(onToggleFocus).toHaveBeenCalledTimes(2);
    expect(onToggleWidth).not.toHaveBeenCalled();

    rerender(
      <DocViewerHeader
        {...baseProps}
        editMode="preview"
        onEditModeChange={() => undefined}
        onViewHistory={() => undefined}
        docFocus
        docWidth="narrow"
        onToggleWidth={onToggleWidth}
        onToggleFocus={onToggleFocus}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "沉静阅读" }));
    expect(onToggleFocus).toHaveBeenCalledTimes(3);
    expect(onToggleWidth).toHaveBeenCalledTimes(1);
  });

  it("puts share on the toolbar instead of the overflow", () => {
    const onShareDoc = vi.fn();
    render(
      <DocViewerHeader
        {...baseProps}
        editMode="preview"
        onEditModeChange={() => undefined}
        onViewHistory={() => undefined}
        onShareDoc={onShareDoc}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "分享" }));
    expect(onShareDoc).toHaveBeenCalledWith("系统/戒律.md", "戒律.md");
    expect(screen.queryByRole("menuitem", { name: "分享" })).toBeNull();
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
