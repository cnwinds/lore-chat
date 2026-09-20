import { describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { PreceptsUpgradeModal } from "./PreceptsUpgradeModal";
import type { PreceptsUpgradePending } from "../../api";

const ours = `# 戒律

## 八、目录规划（知识库归类）
受保护区域：见第七节。

## 九、无痕教学（陪伴学习）
建构优先。

## 附录
只在现行。
`;

const theirs = `# 戒律

## 七、目录规划（知识库归类）
受保护区域：见第六节。

## 八、用户生成 Skill
新建 Skill 包仅当用户明确要求。
`;

const base = `# 戒律

## 八、目录规划（知识库归类）
受保护区域：见第七节。
`;

const pending: PreceptsUpgradePending = {
  official_hash: "abc",
  ours,
  theirs,
  base,
  proposed: ours,
  proposed_source: "fallback",
  marked: "",
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

  it("shows current, result, and official side by side", () => {
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
    expect(screen.getByText("现行")).toBeInTheDocument();
    expect(screen.getByText("官方")).toBeInTheDocument();
    expect(screen.getAllByText(/无痕教学/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/用户生成 Skill/).length).toBeGreaterThan(0);
    const officialHeading = screen.getByText("## 七、目录规划（知识库归类）");
    expect(officialHeading.parentElement).toHaveClass("is-conflict");
    const draft = screen.getByLabelText(/结果/) as HTMLTextAreaElement;
    expect(draft.value).toContain("无痕教学");
    expect(draft.value).toContain("用户生成 Skill");
    expect(draft.value).toContain("附录");
    expect(draft.value).toContain("## 七、目录规划（知识库归类）");
    expect(draft.value).toContain("见第六节");
    expect(draft.value).not.toContain("## 八、目录规划");
    expect(draft.value).not.toContain("见第七节");
    const paintedOfficial = [...document.querySelectorAll(".precepts-merge-origin--theirs")]
      .map((node) => node.textContent ?? "")
      .join("");
    expect(paintedOfficial).toContain("七、目录规划");
    expect(paintedOfficial).toContain("见第六节");
    const paintedLocal = [...document.querySelectorAll(".precepts-merge-origin--ours")]
      .map((node) => node.textContent ?? "")
      .join("");
    expect(paintedLocal).toContain("无痕教学");
  });

  it("uses the complete official side of a hunk", () => {
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
    fireEvent.click(screen.getByRole("tab", { name: /无痕教学/ }));
    fireEvent.click(screen.getByRole("button", { name: "用右边" }));
    expect(screen.getByRole("button", { name: "用右边" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: "写入结果" }));
    const body = onConfirm.mock.calls[0][0] as string;
    expect(body).toContain("用户生成 Skill");
    expect(body).not.toContain("无痕教学");
    expect(body).toContain("附录");
    expect(body).toContain("## 七、目录规划（知识库归类）");
    expect(body).toContain("见第六节");
  });

  it("taking the right side of a whole-file hunk copies the official document", () => {
    const onConfirm = vi.fn();
    const local = "# 戒律\n本地A\n本地B\n";
    const official = "# 戒律\n官方A\n官方B\n官方C\n";
    render(
      <PreceptsUpgradeModal
        open
        pending={{
          ...pending,
          ours: local,
          theirs: official,
          base: "",
          proposed: local,
          conflicts: [{ base: "", ours: local, theirs: official }],
        }}
        proposing={false}
        busy={null}
        error={null}
        onClose={() => undefined}
        onConfirm={onConfirm}
        onDismiss={() => undefined}
        onUseOfficial={() => undefined}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "用右边" }));
    fireEvent.click(screen.getByRole("button", { name: "写入结果" }));
    expect(onConfirm.mock.calls[0][0]).toBe(official);
  });

  it("jumps to the next change from the header", () => {
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
    const next = screen.getByRole("button", { name: "下一处改动" });
    expect(next).not.toBeDisabled();
    fireEvent.click(screen.getByRole("tab", { name: /无痕教学/ }));
    expect(screen.getByRole("tab", { name: /无痕教学/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
});
