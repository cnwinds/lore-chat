import { describe, expect, it, beforeEach } from "vitest";
import { getStoredEditMode, setStoredEditMode } from "./docStorage";

describe("docStorage", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("defaults to preview", () => {
    expect(getStoredEditMode()).toBe("preview");
  });

  it("persists markdown mode", () => {
    setStoredEditMode("markdown");
    expect(getStoredEditMode()).toBe("markdown");
  });
});
