import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useRef } from "react";
import {
  KB_TREE_UI_STORAGE_KEY,
  loadKbTreeUi,
  saveKbTreeScrollTop,
} from "../utils/kbTreeUiStorage";
import { useKbTreeScrollUi } from "./useKbTreeScrollUi";

function makeScrollEl(opts: {
  clientHeight: number;
  scrollHeight: number;
  scrollTop?: number;
}) {
  const state = {
    scrollTop: opts.scrollTop ?? 0,
    clientHeight: opts.clientHeight,
    scrollHeight: opts.scrollHeight,
  };
  const listeners = new Set<EventListener>();
  const el = {
    get scrollTop() {
      return state.scrollTop;
    },
    set scrollTop(v: number) {
      const max = Math.max(0, state.scrollHeight - state.clientHeight);
      state.scrollTop = Math.max(0, Math.min(v, max));
      listeners.forEach((fn) => fn(new Event("scroll")));
    },
    get clientHeight() {
      return state.clientHeight;
    },
    get scrollHeight() {
      return state.scrollHeight;
    },
    setScrollHeight(h: number) {
      state.scrollHeight = h;
    },
    addEventListener: (type: string, fn: EventListener) => {
      if (type === "scroll") listeners.add(fn);
    },
    removeEventListener: (type: string, fn: EventListener) => {
      if (type === "scroll") listeners.delete(fn);
    },
  };
  return el;
}

function renderScrollHook(
  el: ReturnType<typeof makeScrollEl>,
  opts: { collapsed?: boolean; scrollEnabled?: boolean } = {},
) {
  return renderHook(
    ({ collapsed, scrollEnabled }) => {
      const ref = useRef<HTMLElement | null>(el as unknown as HTMLElement);
      return useKbTreeScrollUi(ref, { collapsed, scrollEnabled });
    },
    {
      initialProps: {
        collapsed: opts.collapsed ?? false,
        scrollEnabled: opts.scrollEnabled ?? true,
      },
    },
  );
}

describe("useKbTreeScrollUi", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      return window.setTimeout(
        () => cb(performance.now()),
        0,
      ) as unknown as number;
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it("does not overwrite stored scrollTop with 0 while restore is pending", () => {
    saveKbTreeScrollTop(320);
    const el = makeScrollEl({
      clientHeight: 200,
      scrollHeight: 200,
      scrollTop: 0,
    });

    const { unmount } = renderScrollHook(el);
    // 展开尚未就绪时卸载：不得用 0 冲掉 storage
    unmount();
    expect(loadKbTreeUi()?.scrollTop).toBe(320);
  });

  it("restores scroll once content height can hold stored scrollTop", async () => {
    saveKbTreeScrollTop(320);
    const el = makeScrollEl({
      clientHeight: 200,
      scrollHeight: 200,
      scrollTop: 0,
    });

    const { result } = renderScrollHook(el);

    act(() => {
      el.setScrollHeight(900);
      result.current.onExpandReady();
    });

    await waitFor(() => {
      expect(el.scrollTop).toBe(320);
    });
    // 恢复本身不落盘
    expect(loadKbTreeUi()?.scrollTop).toBe(320);
  });

  it("does not persist clamped scroll when restore gives up early", async () => {
    saveKbTreeScrollTop(500);
    const el = makeScrollEl({
      clientHeight: 200,
      scrollHeight: 220,
      scrollTop: 0,
    });

    const { result, unmount } = renderScrollHook(el);

    act(() => {
      result.current.onExpandReady();
    });

    await waitFor(() => {
      expect(el.scrollTop).toBe(20); // maxScroll only
    });

    unmount();
    expect(loadKbTreeUi()?.scrollTop).toBe(500);
  });

  it("persists scroll only after user scroll post-restore", async () => {
    saveKbTreeScrollTop(100);
    const el = makeScrollEl({
      clientHeight: 200,
      scrollHeight: 800,
      scrollTop: 0,
    });

    const { result } = renderScrollHook(el);

    act(() => {
      result.current.onExpandReady();
    });

    await waitFor(() => {
      expect(el.scrollTop).toBe(100);
    });
    // 程序恢复本身不得改写 storage
    expect(loadKbTreeUi()?.scrollTop).toBe(100);

    act(() => {
      el.scrollTop = 260;
    });

    await waitFor(() => {
      expect(loadKbTreeUi()?.scrollTop).toBe(260);
    });
    expect(localStorage.getItem(KB_TREE_UI_STORAGE_KEY)).toContain("260");
  });
});
