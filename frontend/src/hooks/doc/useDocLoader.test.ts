import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useDocLoader } from "./useDocLoader";

const getDoc = vi.fn();

vi.mock("../../api", () => ({
  getDoc: (...args: unknown[]) => getDoc(...args),
}));

describe("useDocLoader loadDoc position reset", () => {
  beforeEach(() => {
    getDoc.mockReset();
    getDoc.mockResolvedValue({
      rel_path: "notes/a.md",
      meta: {},
      body: "hello world",
    });
  });

  it("moves selection to EOF and bumps previewRemountKey (why local save must skip reload)", async () => {
    const setSelection = vi.fn();
    const setSaveError = vi.fn();
    const setMergeEditing = vi.fn();
    const { result } = renderHook(() =>
      useDocLoader({
        path: "notes/a.md",
        refreshKey: 0,
        setSaveError,
        setMergeEditing,
        setSelection,
      }),
    );
    const remountBefore = result.current.previewRemountKey;
    const gen = ++result.current.loadGenRef.current;

    await act(async () => {
      await result.current.loadDoc("notes/a.md", gen);
    });

    expect(setSelection).toHaveBeenCalledWith({ start: 11, end: 11 });
    expect(result.current.previewRemountKey).toBe(remountBefore + 1);
  });
});
