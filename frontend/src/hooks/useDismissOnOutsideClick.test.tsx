import { createRef, useState } from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useDismissOnOutsideClick } from "./useDismissOnOutsideClick";

function Harness({
  refs,
}: {
  refs: React.RefObject<HTMLElement | null> | React.RefObject<HTMLElement | null>[];
}) {
  const [open, setOpen] = useState(true);
  useDismissOnOutsideClick(refs, open, () => setOpen(false));
  return (
    <div>
      <div data-testid="outside">outside</div>
      <div>{open ? "open" : "closed"}</div>
    </div>
  );
}

describe("useDismissOnOutsideClick", () => {
  it("keeps open when click is inside any of multiple refs", async () => {
    const a = createRef<HTMLDivElement>();
    const b = createRef<HTMLDivElement>();
    const user = userEvent.setup();
    render(
      <>
        <div ref={a} data-testid="a">
          A
        </div>
        <div ref={b} data-testid="b">
          B
        </div>
        <Harness refs={[a, b]} />
      </>,
    );
    expect(screen.getByText("open")).toBeTruthy();
    await user.click(screen.getByTestId("b"));
    expect(screen.getByText("open")).toBeTruthy();
    await user.click(screen.getByTestId("outside"));
    expect(screen.getByText("closed")).toBeTruthy();
  });
});
