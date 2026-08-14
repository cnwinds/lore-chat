import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { buildDocViewerHandlers } from "./buildDocViewerHandlers";
import {
  pathTouchesChanged,
  useDocPreviewLayout,
} from "./useDocPreviewLayout";

describe("pathTouchesChanged", () => {
  it("matches self and ancestor for open file paths", () => {
    expect(pathTouchesChanged("a/b.md", "a/b.md")).toBe(true);
    expect(pathTouchesChanged("a/b.md", "a")).toBe(true);
    expect(pathTouchesChanged("a/b.md", "other")).toBe(false);
  });

  it("matches children when open path is a directory (media gallery)", () => {
    expect(
      pathTouchesChanged("媒体/生成/2026", "媒体/生成/2026/logo.svg"),
    ).toBe(true);
    expect(pathTouchesChanged("媒体/生成/2026", "媒体/生成/2026")).toBe(true);
    expect(pathTouchesChanged("媒体/生成/2026", "媒体/上传/2026/x.png")).toBe(
      false,
    );
  });
});

/**
 * 回归：本地保存 onSaved → refreshKb(path, { except }) 不 bump 本栏 refreshKey，
 * 避免 DocViewer loadDoc → remount 丢滚动/光标；另一栏同路径仍同步。
 */
describe("useDocPreviewLayout refresh after local save", () => {
  it("does not bump the saving pane refreshKey (float)", () => {
    const refreshSidebar = vi.fn();
    const { result } = renderHook(() => useDocPreviewLayout(refreshSidebar));

    act(() => {
      result.current.openDocPreview("notes/a.md");
    });
    const before = result.current.floatRefreshKey;

    act(() => {
      result.current.refreshKb("notes/a.md", { except: "float" });
    });

    expect(refreshSidebar).toHaveBeenCalled();
    expect(result.current.floatRefreshKey).toBe(before);
  });

  it("does not bump the saving pane refreshKey (pinned)", () => {
    const refreshSidebar = vi.fn();
    const { result } = renderHook(() => useDocPreviewLayout(refreshSidebar));

    act(() => {
      result.current.openDocPreview("notes/a.md", undefined, { pin: true });
    });
    const before = result.current.pinnedRefreshKey;

    act(() => {
      result.current.refreshKb("notes/a.md", { except: "pinned" });
    });

    expect(refreshSidebar).toHaveBeenCalled();
    expect(result.current.pinnedRefreshKey).toBe(before);
  });

  it("still bumps the other pane when the same path is open there", () => {
    const refreshSidebar = vi.fn();
    const { result } = renderHook(() => useDocPreviewLayout(refreshSidebar));

    act(() => {
      result.current.openDocPreview("notes/a.md", undefined, { pin: true });
      result.current.openDocPreview("notes/a.md");
    });
    const floatBefore = result.current.floatRefreshKey;
    const pinnedBefore = result.current.pinnedRefreshKey;

    act(() => {
      result.current.refreshKb("notes/a.md", { except: "float" });
    });

    expect(result.current.floatRefreshKey).toBe(floatBefore);
    expect(result.current.pinnedRefreshKey).toBe(pinnedBefore + 1);
  });

  it("external refresh without except still bumps open panes", () => {
    const refreshSidebar = vi.fn();
    const { result } = renderHook(() => useDocPreviewLayout(refreshSidebar));

    act(() => {
      result.current.openDocPreview("notes/a.md", undefined, { pin: true });
    });
    const before = result.current.pinnedRefreshKey;

    act(() => {
      result.current.refreshKb("notes/a.md");
    });

    expect(result.current.pinnedRefreshKey).toBe(before + 1);
  });

  it("bumps media gallery when a file under the open folder changes", () => {
    const refreshSidebar = vi.fn();
    const { result } = renderHook(() => useDocPreviewLayout(refreshSidebar));

    act(() => {
      result.current.openMediaFolder("媒体/生成/2026");
    });
    const before = result.current.mediaRefreshKey;

    act(() => {
      result.current.refreshKb("媒体/生成/2026/logo.svg");
    });

    expect(result.current.mediaRefreshKey).toBe(before + 1);
  });

  it("openMediaFolder ignores non-media paths and keeps pinned", () => {
    const refreshSidebar = vi.fn();
    const { result } = renderHook(() => useDocPreviewLayout(refreshSidebar));

    act(() => {
      result.current.openDocPreview("notes/a.md", undefined, { pin: true });
      result.current.openMediaFolder("备忘");
    });
    expect(result.current.mediaFolderPath).toBeNull();
    expect(result.current.pinnedPath).toBe("notes/a.md");

    act(() => {
      result.current.openMediaFolder("媒体/生成/2026");
    });
    expect(result.current.mediaFolderPath).toBe("媒体/生成/2026");
    expect(result.current.pinnedPath).toBe("notes/a.md");
  });
});

describe("buildDocViewerHandlers onSaved preserves pane position", () => {
  it("wires float onSaved with except:float so refreshKey stays put", () => {
    const refreshSidebar = vi.fn();
    const { result } = renderHook(() => useDocPreviewLayout(refreshSidebar));

    act(() => {
      result.current.openDocPreview("notes/a.md");
    });
    const handlers = buildDocViewerHandlers(result.current, "float", vi.fn());
    const before = result.current.floatRefreshKey;

    act(() => {
      handlers.onSaved("notes/a.md");
    });

    // 位置代理：本栏 refreshKey 不变 → DocViewer 不会 loadDoc remount（滚顶/光标 EOF）
    expect(result.current.floatRefreshKey).toBe(before);
  });

  it("wires pinned onSaved with except:pinned so refreshKey stays put", () => {
    const refreshSidebar = vi.fn();
    const { result } = renderHook(() => useDocPreviewLayout(refreshSidebar));

    act(() => {
      result.current.openDocPreview("notes/a.md", undefined, { pin: true });
    });
    const handlers = buildDocViewerHandlers(result.current, "pinned", vi.fn());
    const before = result.current.pinnedRefreshKey;

    act(() => {
      handlers.onSaved("notes/a.md");
    });

    expect(result.current.pinnedRefreshKey).toBe(before);
  });
});
