import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { FoldChevron } from "./FoldChevron";

afterEach(cleanup);

describe("FoldChevron", () => {
  it("marks the open state so CSS can rotate the stroke", () => {
    const { rerender } = render(<FoldChevron open={false} />);
    expect(document.querySelector(".fold-chevron")).not.toHaveClass("is-open");
    rerender(<FoldChevron open />);
    expect(document.querySelector(".fold-chevron")).toHaveClass("is-open");
  });

  it("uses a down-facing variant for dropdowns", () => {
    render(<FoldChevron open={false} from="down" />);
    expect(document.querySelector(".fold-chevron")).toHaveClass(
      "fold-chevron--from-down",
    );
  });

  it("renders a stroke path instead of a triangle glyph", () => {
    render(<FoldChevron open={false} />);
    const path = document.querySelector(".fold-chevron svg path");
    expect(path).toHaveAttribute("stroke", "currentColor");
    expect(document.querySelector(".fold-chevron")?.textContent).toBe("");
  });
});
