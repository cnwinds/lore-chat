import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CandidateChainEditor } from "./CandidateChainEditor";
import { candidateFromProvider } from "./providerPresets";

afterEach(() => {
  cleanup();
});

function renderChain(onChange: ReturnType<typeof vi.fn> = vi.fn()) {
  const a = { ...candidateFromProvider("zhipu"), id: "a", model: "glm-a" };
  const b = { ...candidateFromProvider("deepseek"), id: "b", model: "ds-b" };
  const result = render(
    <CandidateChainEditor
      title="对话链"
      candidates={[a, b]}
      onChange={onChange}
      cooldown={{}}
      onClearCooldown={vi.fn()}
      saving={false}
      attention
    />,
  );
  return { ...result, onChange, a, b };
}

describe("CandidateChainEditor reorder", () => {
  it("uses a drag handle instead of up/down buttons", () => {
    renderChain();
    expect(screen.queryByRole("button", { name: "上移" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "下移" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "拖动调整顺序" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "删除" })).toHaveLength(2);
  });

  it("reorders with arrow keys on the drag handle", async () => {
    const user = userEvent.setup();
    const { onChange, a, b } = renderChain();
    const grips = screen.getAllByRole("button", { name: "拖动调整顺序" });
    grips[1].focus();
    await user.keyboard("{ArrowUp}");
    expect(onChange).toHaveBeenCalledWith([b, a]);
  });

  it("reorders by dropping a handle onto another row", () => {
    const { onChange, a, b } = renderChain();
    const dt = {
      setData: vi.fn(),
      effectAllowed: "move",
      dropEffect: "move",
    };
    const grips = screen.getAllByRole("button", { name: "拖动调整顺序" });
    fireEvent.dragStart(grips[0], { dataTransfer: dt });
    const rows = document.querySelectorAll(".settings-model-candidate");
    fireEvent.dragOver(rows[1], { dataTransfer: dt });
    fireEvent.drop(rows[1], { dataTransfer: dt });
    expect(onChange).toHaveBeenCalledWith([b, a]);
  });
});
