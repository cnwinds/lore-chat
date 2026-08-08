import { describe, expect, it } from "vitest";
import {
  applyInjectDeferred,
  applyStreamEnd,
  applyUserInjected,
} from "./outboundQueue";
import type { SendQueueItem } from "../../utils/sendQueue";

function item(partial: Partial<SendQueueItem> & { id: string }): SendQueueItem {
  return {
    text: "hi",
    timing: "defer",
    mergeWithNext: false,
    webEnabled: false,
    locked: false,
    error: null,
    ...partial,
  };
}

describe("outboundQueue policy", () => {
  it("detached does not pause", () => {
    const out = applyStreamEnd(
      {
        items: [item({ id: "a" })],
        paused: false,
        pendingGroup: null,
        flushing: true,
      },
      { failed: false, aborted: false, detached: true },
    );
    expect(out.paused).toBe(false);
    expect(out.flushing).toBe(false);
    expect(out.shouldFlush).toBe(false);
  });

  it("failure restores pending and pauses", () => {
    const pending = [item({ id: "p" })];
    const out = applyStreamEnd(
      {
        items: [item({ id: "a" })],
        paused: false,
        pendingGroup: pending,
        flushing: true,
      },
      { failed: true, aborted: false },
    );
    expect(out.paused).toBe(true);
    expect(out.items[0].id).toBe("p");
    expect(out.items[0].error).toBe("发送失败");
    expect(out.shouldFlush).toBe(false);
  });

  it("awaitingUser pauses without flush", () => {
    const out = applyStreamEnd(
      {
        items: [item({ id: "a" })],
        paused: false,
        pendingGroup: null,
        flushing: true,
      },
      { failed: false, aborted: false, awaitingUser: true },
    );
    expect(out.paused).toBe(true);
    expect(out.shouldFlush).toBe(false);
  });

  it("success schedules flush", () => {
    const out = applyStreamEnd(
      {
        items: [item({ id: "a" })],
        paused: false,
        pendingGroup: null,
        flushing: true,
      },
      { failed: false, aborted: false },
    );
    expect(out.shouldFlush).toBe(true);
    expect(out.flushing).toBe(false);
  });

  it("inject deferred unlocks to defer", () => {
    const next = applyInjectDeferred(
      [item({ id: "i1", locked: true, timing: "inject" })],
      "i1",
    );
    expect(next[0].locked).toBe(false);
    expect(next[0].timing).toBe("defer");
  });

  it("user injected removes locked group", () => {
    const next = applyUserInjected(
      [item({ id: "i1", locked: true }), item({ id: "b" })],
      "i1",
    );
    expect(next.map((x) => x.id)).toEqual(["b"]);
  });
});
