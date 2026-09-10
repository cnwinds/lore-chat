import { describe, expect, it } from "vitest";
import { routineListTitle } from "./routineTitle";

describe("routineListTitle", () => {
  it("uses the first line and truncates long prompts", () => {
    expect(routineListTitle("每日简报")).toBe("每日简报");
    expect(routineListTitle("第一行\n第二行")).toBe("第一行");
    expect(routineListTitle("")).toBe("未命名任务");
    expect(routineListTitle("x".repeat(40))).toBe(`${"x".repeat(28)}…`);
  });
});
