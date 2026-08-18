import { describe, expect, it } from "vitest";
import { anchoredMenuBox } from "./anchoredMenuBox";

const menu = { width: 168, height: 80 };

describe("anchoredMenuBox", () => {
  it("opens below when the first row has room under the trigger", () => {
    const box = anchoredMenuBox(
      { top: 120, bottom: 148, left: 400, right: 428 },
      menu,
      { width: 800, height: 600 },
      { align: "end" },
    );
    expect(box.top).toBe(152);
    expect(box.left).toBe(428 - 168);
  });

  it("opens above when there is no room below (last row)", () => {
    const box = anchoredMenuBox(
      { top: 540, bottom: 568, left: 400, right: 428 },
      menu,
      { width: 800, height: 600 },
      { align: "end" },
    );
    expect(box.top).toBe(540 - 4 - 80);
  });

  it("clamps horizontally into the viewport", () => {
    const box = anchoredMenuBox(
      { top: 100, bottom: 128, left: 10, right: 40 },
      menu,
      { width: 200, height: 400 },
      { align: "end" },
    );
    expect(box.left).toBe(8);
  });
});
