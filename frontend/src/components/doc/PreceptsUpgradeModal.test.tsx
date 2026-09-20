import { describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { PreceptsUpgradeModal } from "./PreceptsUpgradeModal";
import type { PreceptsUpgradePending } from "../../api";

const ours = `# 戒律

## 八、目录规划
受保护区域。

## 九、无痕教学（陪伴学习）
建构优先。

## 附录
只在现行。
`;

const theirs = `# 戒律

## 七、目录规划
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
  marked: `${base}<<<<<<< 当前
## 九、无痕教学（陪伴学习）
建构优先。
||||||| 上次官方
=======
## 八、用户生成 Skill
新建 Skill 包仅当用户明确要求。
>>>>>>> 新官方
`,
  conflicts: [
    {
      base: "",
      ours: "## 九、无痕教学（陪伴学习）\n建构优先。\n",
      theirs: "## 八、用户生成 Skill\n新建 Skill 包仅当用户明确要求。\n",
    },
  ],
  created_at: "2026-09-19T16:00:00+08:00",
};

describe("PreceptsUpgradeModal", () => {
  beforeEach(() => {
    cleanup();
  });

  it("shows a git-style hunk instead of tabs", () => {
    render(
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
      />,
    );
    expect(screen.getByRole("dialog", { name: "戒律更新" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "合一" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "两段都留" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByText(/现行多了「附录」/)).toBeInTheDocument();
    expect(screen.getAllByText("现行").length).toBeGreaterThan(0);
    expect(screen.getAllByText("官方").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/无痕教学/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/用户生成 Skill/).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "合并稿" })).toBeNull();
    expect(screen.queryByRole("button", { name: "对照" })).toBeNull();
    const draft = screen.getByLabelText(/将写入/) as HTMLTextAreaElement;
    expect(draft.value).toContain("无痕教学");
    expect(draft.value).toContain("用户生成 Skill");
    expect(draft.value).toContain("附录");
  });

  it("can switch to a side-by-side hunk", () => {
    render(
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
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "并排" }));
    expect(screen.getByRole("button", { name: "并排" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getAllByText("现行").length).toBeGreaterThan(0);
  });

  it("writes the merge result, not a hidden tab", () => {
    const onConfirm = vi.fn();
    render(
      <PreceptsUpgradeModal
        open
        pending={pending}
        proposing={false}
        busy={null}
        error={null}
        onClose={() => undefined}
        onConfirm={onConfirm}
        onDismiss={() => undefined}
        onUseOfficial={() => undefined}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "用官方" }));
    expect(screen.getByRole("button", { name: "用官方" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: "写入结果" }));
    expect(onConfirm).toHaveBeenCalled();
    const body = onConfirm.mock.calls[0][0] as string;
    expect(body).toContain("用户生成 Skill");
    expect(body).not.toContain("无痕教学");
    expect(body).toContain("附录");
  });
});
