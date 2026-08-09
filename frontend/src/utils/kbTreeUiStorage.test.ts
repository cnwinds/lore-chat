import { beforeEach, describe, expect, it } from "vitest";
import {
  KB_TREE_UI_STORAGE_KEY,
  hasPersistedExpanded,
  loadKbTreeUi,
  patchKbTreeUi,
  saveKbTreeExpanded,
  saveKbTreeExpandedIfPersisted,
  saveKbTreeScrollTop,
} from "./kbTreeUiStorage";

describe("kbTreeUiStorage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns null when never saved", () => {
    expect(loadKbTreeUi()).toBeNull();
    expect(hasPersistedExpanded()).toBe(false);
  });

  it("persists expanded paths without forcing scrollTop", () => {
    saveKbTreeExpanded(["a", "a/b"]);
    expect(loadKbTreeUi()).toEqual({ expandedPaths: ["a", "a/b"] });
    expect(hasPersistedExpanded()).toBe(true);
  });

  it("persists scrollTop without forcing expandedPaths", () => {
    saveKbTreeScrollTop(240);
    expect(loadKbTreeUi()).toEqual({ scrollTop: 240 });
    expect(hasPersistedExpanded()).toBe(false);
  });

  it("merges expanded and scroll across patches", () => {
    saveKbTreeExpanded(["docs"]);
    saveKbTreeScrollTop(80);
    expect(loadKbTreeUi()).toEqual({
      expandedPaths: ["docs"],
      scrollTop: 80,
    });
    patchKbTreeUi({ expandedPaths: ["docs", "docs/x"] });
    expect(loadKbTreeUi()).toEqual({
      expandedPaths: ["docs", "docs/x"],
      scrollTop: 80,
    });
  });

  it("saveKbTreeExpandedIfPersisted skips until user has toggled", () => {
    saveKbTreeExpandedIfPersisted(["a"]);
    expect(loadKbTreeUi()).toBeNull();
    saveKbTreeScrollTop(10);
    saveKbTreeExpandedIfPersisted(["a"]);
    expect(loadKbTreeUi()).toEqual({ scrollTop: 10 });
    saveKbTreeExpanded(["b"]);
    saveKbTreeExpandedIfPersisted(["a", "b"]);
    expect(loadKbTreeUi()).toEqual({
      expandedPaths: ["a", "b"],
      scrollTop: 10,
    });
  });

  it("ignores corrupt storage", () => {
    localStorage.setItem(KB_TREE_UI_STORAGE_KEY, "{not-json");
    expect(loadKbTreeUi()).toBeNull();
  });

  it("clamps negative scrollTop", () => {
    saveKbTreeScrollTop(-12);
    expect(loadKbTreeUi()?.scrollTop).toBe(0);
  });
});
