import { act, renderHook } from "@testing-library/react";
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

function flushRaf(rafQueue: FrameRequestCallback[], n = 1) {
  for (let i = 0; i < n; i++) {
    const cb = rafQueue.shift();
    if (!cb) break;
    cb(performance.now());
  }
}

describe("useKbTreeScrollUi", () => {
  let rafQueue: FrameRequestCallback[];

  beforeEach(() => {
    localStorage.clear();
    rafQueue = [];
    vi.useFakeTimers();
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      rafQueue.push(cb);
      return rafQueue.length;
    });
    vi.stubGlobal("cancelAnimationFrame", (id: number) => {
      const idx = id - 1;
      if (idx >= 0 && idx < rafQueue.length) {
        rafQueue[idx] = () => {};
      }
    });
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
        unobserve() {}
      },
    );
  });

  afterEach(() => {
    vi.useRealTimers();
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
    unmount();
    expect(loadKbTreeUi()?.scrollTop).toBe(320);
  });

  it("restores scroll on a later frame when content height grows", () => {
    saveKbTreeScrollTop(320);
    const el = makeScrollEl({
      clientHeight: 200,
      scrollHeight: 200,
      scrollTop: 0,
    });

    const { result } = renderScrollHook(el);

    act(() => {
      result.current.onExpandReady();
    });
    expect(rafQueue.length).toBe(1);

    act(() => {
      flushRaf(rafQueue, 1);
    });
    // 高度不够：继续排队下一帧，不落盘
    expect(el.scrollTop).toBe(0);
    expect(rafQueue.length).toBe(1);
    expect(loadKbTreeUi()?.scrollTop).toBe(320);

    act(() => {
      el.setScrollHeight(900);
      flushRaf(rafQueue, 1);
    });
    expect(el.scrollTop).toBe(320);
    expect(loadKbTreeUi()?.scrollTop).toBe(320);
  });

  it("does not persist clamped scroll when restore times out", () => {
    saveKbTreeScrollTop(500);
    const el = makeScrollEl({
      clientHeight: 200,
      scrollHeight: 220,
      scrollTop: 0,
    });

    let now = 0;
    vi.spyOn(performance, "now").mockImplementation(() => now);

    const { result, unmount } = renderScrollHook(el);

    act(() => {
      result.current.onExpandReady();
    });

    act(() => {
      flushRaf(rafQueue, 1);
    });
    expect(el.scrollTop).toBe(0);
    expect(rafQueue.length).toBe(1);

    now = 2500;
    act(() => {
      flushRaf(rafQueue, 1);
    });
    expect(el.scrollTop).toBe(20);

    unmount();
    expect(loadKbTreeUi()?.scrollTop).toBe(500);
  });

  it("persists scroll only after user scroll post-restore", () => {
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
    act(() => {
      flushRaf(rafQueue, 1);
    });
    expect(el.scrollTop).toBe(100);
    expect(loadKbTreeUi()?.scrollTop).toBe(100);

    act(() => {
      el.scrollTop = 260;
    });
    act(() => {
      vi.advanceTimersByTime(120);
    });

    expect(loadKbTreeUi()?.scrollTop).toBe(260);
    expect(localStorage.getItem(KB_TREE_UI_STORAGE_KEY)).toContain("260");
  });
});
