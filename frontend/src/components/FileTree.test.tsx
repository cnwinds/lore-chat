import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FileTree } from "./FileTree";
import {
  buildFileTree,
  MEDIA_DIR,
  MEMORY_DIR,
  SKILLS_DIR,
  SYSTEM_LAYER_DIR,
} from "../utils/fileTree";

afterEach(cleanup);

const noop = vi.fn();

function renderTree(
  tree = buildFileTree(["业务/a.md"]),
  extra?: { expanded?: Set<string> },
) {
  return render(
    <FileTree
      tree={tree}
      onSelectFile={noop}
      dropHighlightDir={null}
      onDropHighlightDir={noop}
      onDropFiles={noop}
      onMovePath={noop}
      onContextMenu={noop}
      renamingPath={null}
      renamingValue=""
      onRenamingValueChange={noop}
      onRenameCommit={noop}
      onRenameCancel={noop}
      onStartRename={noop}
      expanded={extra?.expanded ?? new Set()}
      onToggleFolder={noop}
    />,
  );
}

describe("FileTree special group", () => {
  it("wraps 系统 / 技能 / 记忆 / 媒体 in one shell and leaves user folders outside", () => {
    renderTree();
    const group = document.querySelector(".file-tree-special-group");
    expect(group).toBeTruthy();
    expect(group?.querySelector(`[data-kb-path="${SYSTEM_LAYER_DIR}"]`)).toBeTruthy();
    expect(group?.querySelector(`[data-kb-path="${SKILLS_DIR}"]`)).toBeTruthy();
    expect(group?.querySelector(`[data-kb-path="${MEMORY_DIR}"]`)).toBeTruthy();
    expect(group?.querySelector(`[data-kb-path="${MEDIA_DIR}"]`)).toBeTruthy();
    const business = screen.getByText("业务").closest(".file-tree-row");
    expect(business).toBeTruthy();
    expect(group?.contains(business)).toBe(false);
  });

  it("keeps expanded special descendants inside the same shell", () => {
    const tree = buildFileTree([`${SYSTEM_LAYER_DIR}/心法.md`, "业务/a.md"]);
    renderTree(tree, { expanded: new Set([SYSTEM_LAYER_DIR]) });
    const group = document.querySelector(".file-tree-special-group");
    expect(group?.querySelector('[data-kb-path="系统/心法.md"]')).toBeTruthy();
    const business = screen.getByText("业务").closest(".file-tree-row");
    expect(group?.contains(business)).toBe(false);
  });
});

describe("FileTree precepts attention", () => {
  const preceptsTree = buildFileTree([`${SYSTEM_LAYER_DIR}/戒律.md`]);

  it("marks 系统 when collapsed", () => {
    render(
      <FileTree
        tree={preceptsTree}
        onSelectFile={noop}
        dropHighlightDir={null}
        onDropHighlightDir={noop}
        onDropFiles={noop}
        onMovePath={noop}
        onContextMenu={noop}
        renamingPath={null}
        renamingValue=""
        onRenamingValueChange={noop}
        onRenameCommit={noop}
        onRenameCancel={noop}
        onStartRename={noop}
        expanded={new Set()}
        onToggleFolder={noop}
        preceptsAttention
        preceptsPath={`${SYSTEM_LAYER_DIR}/戒律.md`}
      />,
    );
    const folder = document.querySelector(
      `[data-kb-path="${SYSTEM_LAYER_DIR}"]`,
    );
    expect(folder?.querySelector(".settings-attention-dot")).toBeTruthy();
    expect(
      document.querySelector(`[data-kb-path="${SYSTEM_LAYER_DIR}/戒律.md"]`),
    ).toBeNull();
  });

  it("marks 系统 and 戒律.md when expanded", () => {
    render(
      <FileTree
        tree={preceptsTree}
        onSelectFile={noop}
        dropHighlightDir={null}
        onDropHighlightDir={noop}
        onDropFiles={noop}
        onMovePath={noop}
        onContextMenu={noop}
        renamingPath={null}
        renamingValue=""
        onRenamingValueChange={noop}
        onRenameCommit={noop}
        onRenameCancel={noop}
        onStartRename={noop}
        expanded={new Set([SYSTEM_LAYER_DIR])}
        onToggleFolder={noop}
        preceptsAttention
        preceptsPath={`${SYSTEM_LAYER_DIR}/戒律.md`}
      />,
    );
    expect(
      document.querySelector(
        `[data-kb-path="${SYSTEM_LAYER_DIR}"] .settings-attention-dot`,
      ),
    ).toBeTruthy();
    expect(
      document.querySelector(
        `[data-kb-path="${SYSTEM_LAYER_DIR}/戒律.md"] .settings-attention-dot`,
      ),
    ).toBeTruthy();
    expect(screen.getAllByTitle("有待确认的戒律更新")).toHaveLength(2);
  });
});
