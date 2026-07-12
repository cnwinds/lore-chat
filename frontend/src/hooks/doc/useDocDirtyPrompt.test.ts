import { describe, expect, it } from "vitest";
import { nextUnsavedAfterDiscard } from "./useDocDirtyPrompt";

describe("nextUnsavedAfterDiscard", () => {
  it("close prompt clears and signals finishClose", () => {
    expect(nextUnsavedAfterDiscard("close")).toEqual({ kind: "finishClose" });
  });

  it("navigate prompt signals completeNavigation", () => {
    expect(nextUnsavedAfterDiscard("navigate")).toEqual({
      kind: "completeNavigation",
    });
  });

  it("reload prompt signals completeNavigation", () => {
    expect(nextUnsavedAfterDiscard("reload")).toEqual({
      kind: "completeNavigation",
    });
  });

  it("view prompt is a noop", () => {
    expect(nextUnsavedAfterDiscard("view")).toEqual({ kind: "noop" });
  });
});
