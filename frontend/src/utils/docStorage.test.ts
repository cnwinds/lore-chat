import { describe, expect, it, beforeEach } from "vitest";
import {
  getStoredFloatWidth,
  getStoredPanelWidth,
  getStoredEditMode,
  setStoredFloatWidth,
  setStoredPanelWidth,
  setStoredEditMode,
} from "./docStorage";

describe("docStorage", () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  it("defaults to preview", () => {
    expect(getStoredEditMode()).toBe("preview");
  });

  it("persists markdown mode", () => {
    setStoredEditMode("markdown");
    expect(getStoredEditMode()).toBe("markdown");
  });

  it("defaults float width to narrow", () => {
    expect(getStoredFloatWidth()).toBe("narrow");
  });

  it("persists float width", () => {
    setStoredFloatWidth("wide");
    expect(getStoredFloatWidth()).toBe("wide");
  });

  it("defaults panel width to narrow", () => {
    expect(getStoredPanelWidth()).toBe("narrow");
  });

  it("persists panel width independently from float", () => {
    setStoredFloatWidth("wide");
    setStoredPanelWidth("narrow");
    expect(getStoredFloatWidth()).toBe("wide");
    expect(getStoredPanelWidth()).toBe("narrow");
    setStoredPanelWidth("wide");
    expect(getStoredPanelWidth()).toBe("wide");
    expect(getStoredFloatWidth()).toBe("wide");
  });
});
