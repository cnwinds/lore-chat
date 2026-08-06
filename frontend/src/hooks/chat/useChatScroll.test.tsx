import { act, cleanup, render, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useChatScroll } from "./useChatScroll";

function mockScrollBox(
  el: HTMLElement,
  opts: { scrollHeight: number; clientHeight: number; scrollTop: number },
) {
  Object.defineProperty(el, "scrollHeight", {
    configurable: true,
    get: () => opts.scrollHeight,
  });
  Object.defineProperty(el, "clientHeight", {
    configurable: true,
    get: () => opts.clientHeight,
  });
  Object.defineProperty(el, "scrollTop", {
    configurable: true,
    get: () => opts.scrollTop,
    set: (v: number) => {
      opts.scrollTop = v;
    },
  });
}

describe("useChatScroll", () => {
  let rafQueue: FrameRequestCallback[];

  beforeEach(() => {
    rafQueue = [];
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
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("exposes stickToBottom ref default true", () => {
    const { result } = renderHook(() => useChatScroll());
    expect(result.current.stickToBottomRef.current).toBe(true);
  });

  it("unsticks immediately on upward wheel and cancels pending auto-scroll", () => {
    const dims = { scrollHeight: 2000, clientHeight: 500, scrollTop: 1500 };
    let stick = true;
    const stickRef = {
      get current() {
        return stick;
      },
      set current(v: boolean) {
        stick = v;
      },
    };

    function Harness({ tick }: { tick: number }) {
      const { messagesContainerRef } = useChatScroll([tick], stickRef);
      return <div ref={messagesContainerRef} data-testid="box" />;
    }

    const { rerender, getByTestId } = render(<Harness tick={0} />);
    const el = getByTestId("box");
    mockScrollBox(el, dims);

    act(() => {
      rerender(<Harness tick={1} />);
    });
    expect(rafQueue.length).toBeGreaterThan(0);
    expect(stick).toBe(true);

    act(() => {
      el.dispatchEvent(new WheelEvent("wheel", { deltaY: -40, bubbles: true }));
    });
    expect(stick).toBe(false);

    const topBefore = dims.scrollTop;
    act(() => {
      const queued = [...rafQueue];
      rafQueue.length = 0;
      for (const cb of queued) cb(0);
    });
    expect(dims.scrollTop).toBe(topBefore);
    expect(stick).toBe(false);
  });

  it("unsticks when scroll leaves a tight bottom threshold", () => {
    let stick = true;
    const stickRef = {
      get current() {
        return stick;
      },
      set current(v: boolean) {
        stick = v;
      },
    };

    function Harness() {
      const { messagesContainerRef } = useChatScroll([], stickRef);
      return <div ref={messagesContainerRef} data-testid="box" />;
    }

    const { getByTestId } = render(<Harness />);
    const el = getByTestId("box");
    const dims = { scrollHeight: 2000, clientHeight: 500, scrollTop: 1500 };
    mockScrollBox(el, dims);

    // 30px from bottom — old 80px threshold would still stick.
    dims.scrollTop = 1470;
    act(() => {
      el.dispatchEvent(new Event("scroll"));
    });
    expect(stick).toBe(false);
  });
});
