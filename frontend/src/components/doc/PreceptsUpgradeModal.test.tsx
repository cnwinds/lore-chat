import { describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { PreceptsUpgradeModal } from "./PreceptsUpgradeModal";
import type { PreceptsUpgradePending } from "../../api";

// 两处互不重叠的冲突：首行改写 + 文末各自追加不同小节
const ours = `# 戒律（现行改）

## 八、目录规划
受保护区域。

## 九、无痕教学（陪伴学习）
建构优先。

## 附录
只在现行。
`;

const theirs = `# 戒律（官方改）

## 八、目录规划
受保护区域。

## 八、用户生成 Skill
新建 Skill 包仅当用户明确要求。
`;

const base = `# 戒律

## 八、目录规划
受保护区域。
`;

const pending: PreceptsUpgradePending = {
  official_hash: "abc",
  ours,
  theirs,
  base,
  proposed: ours,
  proposed_source: "fallback",
  conflicts: [],
  created_at: "2026-09-19T16:00:00+08:00",
};

function renderModal(
  overrides: Partial<Parameters<typeof PreceptsUpgradeModal>[0]> = {},
) {
  return render(
    <PreceptsUpgradeModal
      open
      pending={pending}
      proposing={false}
      busy={null}
      error={null}
      onClose={() => undefined}
      onConfirm={() => undefined}
      onDismiss={() => undefined}
      onUseOfficial={() => undefined}
      {...overrides}
    />,
  );
}

describe("PreceptsUpgradeModal", () => {
  beforeEach(() => {
    cleanup();
  });

  it("shows current, result, and official panes with pending conflicts", () => {
    renderModal();
    expect(screen.getByRole("dialog", { name: "戒律更新" })).toBeInTheDocument();
    expect(screen.getAllByText("现行").length).toBeGreaterThan(0);
    expect(screen.getAllByText("官方").length).toBeGreaterThan(0);
    expect(screen.getByText("结果")).toBeInTheDocument();
    expect(screen.getByText("2 处改动，2 处待定")).toBeInTheDocument();
    // 默认冲突区保持现行内容
    const editor = screen.getByLabelText("合并结果编辑") as HTMLTextAreaElement;
    expect(editor.value).toContain("戒律（现行改）");
    expect(editor.value).toContain("无痕教学");
    expect(editor.value).toContain("附录");
  });

  it("resolves conflicts from the middle buttons and writes the result", () => {
    const onConfirm = vi.fn();
    renderModal({ onConfirm });
    const resultPane = within(screen.getByLabelText("结果，可编辑"));
    const official = resultPane.getAllByTitle("用官方");
    expect(official).toHaveLength(2);
    fireEvent.click(official[0]);
    expect(screen.getByText("还有 1 处冲突待处理")).toBeInTheDocument();
    fireEvent.click(resultPane.getAllByTitle("用官方")[1]);
    expect(screen.getByText("冲突都已处理，可直接写入")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "写入结果" }));
    expect(onConfirm).toHaveBeenCalled();
    const body = onConfirm.mock.calls[0][0] as string;
    expect(body).toContain("用户生成 Skill");
    expect(body).toContain("戒律（官方改）");
    expect(body).not.toContain("无痕教学");
  });

  it("keeps a manual edit when picking the official side afterwards", () => {
    renderModal();
    const editor = screen.getByLabelText("合并结果编辑") as HTMLTextAreaElement;
    fireEvent.change(editor, {
      target: { value: editor.value.replace("只在现行。", "手工改。") },
    });
    fireEvent.click(
      within(screen.getByLabelText("结果，可编辑")).getAllByTitle("用官方")[0],
    );
    const value = (screen.getByLabelText("合并结果编辑") as HTMLTextAreaElement)
      .value;
    expect(value).toContain("手工改。");
    expect(value).toContain("戒律（官方改）");
    expect(screen.getByText("冲突都已处理，可直接写入")).toBeInTheDocument();
  });

  it("navigates chunks with prev/next", () => {
    renderModal();
    expect(screen.getByText("1/2")).toBeInTheDocument();
    const prev = screen.getByRole("button", { name: "上一处" });
    expect(prev).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "下一处" }));
    expect(screen.getByText("2/2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "下一处" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "上一处" }));
    expect(screen.getByText("1/2")).toBeInTheDocument();
  });

  it("resolves all conflicts to one side from the toolbar", () => {
    const onConfirm = vi.fn();
    renderModal({ onConfirm });
    fireEvent.click(screen.getByRole("button", { name: "冲突全用官方" }));
    expect(screen.getByText("冲突都已处理，可直接写入")).toBeInTheDocument();
    const editor = screen.getByLabelText("合并结果编辑") as HTMLTextAreaElement;
    expect(editor.value).toContain("用户生成 Skill");
    expect(editor.value).not.toContain("无痕教学");
    fireEvent.click(screen.getByRole("button", { name: "写入结果" }));
    expect(onConfirm).toHaveBeenCalled();
  });

  it("ignores a conflict without changing the result", () => {
    renderModal();
    fireEvent.click(screen.getAllByTitle("保持现状，不再提示")[0]);
    const editor = screen.getByLabelText("合并结果编辑") as HTMLTextAreaElement;
    expect(editor.value).toContain("戒律（现行改）");
    expect(screen.getByText("还有 1 处冲突待处理")).toBeInTheDocument();
  });
});
