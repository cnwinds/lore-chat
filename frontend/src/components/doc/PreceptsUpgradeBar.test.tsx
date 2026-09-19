import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { PreceptsUpgradeBar } from "./PreceptsUpgradeBar";

describe("PreceptsUpgradeBar", () => {
  it("adopts from the bar", () => {
    const onConfirm = vi.fn();
    render(
      <PreceptsUpgradeBar
        proposing={false}
        busy={null}
        onReview={() => undefined}
        onConfirm={onConfirm}
        onDismiss={() => undefined}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "采用" }));
    expect(onConfirm).toHaveBeenCalled();
  });
});
