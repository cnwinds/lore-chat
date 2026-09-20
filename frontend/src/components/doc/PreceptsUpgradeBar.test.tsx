import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { PreceptsUpgradeBar } from "./PreceptsUpgradeBar";

describe("PreceptsUpgradeBar", () => {
  it("opens the comparison instead of writing blindly", () => {
    const onReview = vi.fn();
    render(
      <PreceptsUpgradeBar
        proposing={false}
        busy={null}
        onReview={onReview}
        onDismiss={() => undefined}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "对照" }));
    expect(onReview).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "采用" })).toBeNull();
  });
});
