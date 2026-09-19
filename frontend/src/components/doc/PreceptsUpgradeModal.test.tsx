import { describe, expect, it, vi, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { PreceptsUpgradeModal } from "./PreceptsUpgradeModal";
import type { PreceptsUpgradePending } from "../../api";

const pending: PreceptsUpgradePending = {
  official_hash: "abc",
  ours: "当前全文\n必须先问用户\n",
  theirs: "官方全文\n宁可先不记\n",
  base: "旧官方\n宁可不记\n",
  proposed: "合并全文\n必须先问；宁可先不记。\n",
  proposed_source: "ai",
  conflicts: [
    {
      base: "宁可不记\n",
      ours: "必须先问用户\n",
      theirs: "宁可先不记\n",
    },
  ],
  created_at: "2026-09-19T16:00:00+08:00",
};

describe("PreceptsUpgradeModal", () => {
  beforeEach(() => {
    cleanup();
  });

  it("shows conflict hunks and confirms the draft", () => {
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
    expect(screen.getByRole("dialog", { name: "戒律更新" })).toBeInTheDocument();
    expect(screen.getByText("必须先问用户")).toBeInTheDocument();
    expect(screen.getByText("宁可先不记")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "合并稿" }));
    fireEvent.click(screen.getByRole("button", { name: "采用" }));
    expect(onConfirm).toHaveBeenCalledWith(pending.proposed);
  });
});
