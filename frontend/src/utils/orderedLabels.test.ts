import { describe, expect, it } from "vitest";
import { labelFor, orderedKeys } from "./orderedLabels";

describe("orderedKeys", () => {
  it("puts known keys first then sorts the rest", () => {
    expect(orderedKeys(["z", "b", "a"], ["a", "b"])).toEqual(["a", "b", "z"]);
  });
});

describe("labelFor", () => {
  it("falls back to the raw key", () => {
    expect(labelFor("name", { name: "名称" })).toBe("名称");
    expect(labelFor("custom", { name: "名称" })).toBe("custom");
  });
});
