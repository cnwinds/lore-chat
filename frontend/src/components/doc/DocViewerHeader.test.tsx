import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { DocViewerHeader } from "./DocViewerHeader";

describe("DocViewerHeader", () => {
  it("shows a labeled revision button", () => {
    const onViewHistory = vi.fn();
    render(
      <DocViewerHeader
        mode="float"
        path="系统/戒律.md"
        doc={{ rel_path: "系统/戒律.md", meta: { title: "戒律" }, body: "" }}
        dirty={false}
        onClose={() => undefined}
        editMode="preview"
        onEditModeChange={() => undefined}
        loading={false}
        mergeEditing={false}
        readOnly={false}
        saving={false}
        mergeReview={null}
        onDiscard={() => undefined}
        onSave={() => undefined}
        onMergeSave={() => undefined}
        onViewDiff={() => undefined}
        onViewHistory={onViewHistory}
        outlineOpen={false}
        onOutlineToggle={() => undefined}
        onOutlineClose={() => undefined}
        outlineItems={[]}
        outlineActiveIndex={-1}
        onOutlineJump={() => undefined}
        docWidth="wide"
        docFocus={false}
        onToggleWidth={() => undefined}
        onToggleFocus={() => undefined}
        onMergeEditingToggle={() => undefined}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "修订" }));
    expect(onViewHistory).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "收窄阅读区" })).toHaveClass(
      "doc-toolbar-wide-only",
    );
    expect(screen.getByRole("button", { name: "专注阅读" })).toHaveClass(
      "doc-toolbar-wide-only",
    );
  });
});
