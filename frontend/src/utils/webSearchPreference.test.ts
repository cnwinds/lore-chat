import { afterEach, describe, expect, it } from "vitest";
import {
  WEB_SEARCH_CHANGED_EVENT,
  WEB_SEARCH_STORAGE_KEY,
  maybeEnableComposerWebSearch,
  readWebSearchEnabled,
  writeWebSearchEnabled,
} from "./webSearchPreference";

afterEach(() => {
  localStorage.removeItem(WEB_SEARCH_STORAGE_KEY);
});

describe("webSearchPreference", () => {
  it("defaults off", () => {
    expect(readWebSearchEnabled()).toBe(false);
  });

  it("persists and notifies", () => {
    const seen: boolean[] = [];
    const onChange = (e: Event) => {
      seen.push((e as CustomEvent<{ enabled: boolean }>).detail.enabled);
    };
    window.addEventListener(WEB_SEARCH_CHANGED_EVENT, onChange);
    writeWebSearchEnabled(true);
    expect(readWebSearchEnabled()).toBe(true);
    expect(seen).toEqual([true]);
    writeWebSearchEnabled(false);
    expect(readWebSearchEnabled()).toBe(false);
    expect(seen).toEqual([true, false]);
    window.removeEventListener(WEB_SEARCH_CHANGED_EVENT, onChange);
  });
});

describe("maybeEnableComposerWebSearch", () => {
  it("turns on only when search first becomes configured", () => {
    expect(maybeEnableComposerWebSearch(false, false)).toBe(false);
    expect(readWebSearchEnabled()).toBe(false);

    expect(maybeEnableComposerWebSearch(false, true)).toBe(true);
    expect(readWebSearchEnabled()).toBe(true);

    writeWebSearchEnabled(false);
    expect(maybeEnableComposerWebSearch(true, true)).toBe(false);
    expect(readWebSearchEnabled()).toBe(false);
  });
});
