import { describe, expect, it } from "vitest";
import {
  loadSendQueue,
  mergeGroupText,
  saveSendQueue,
  takeNextGroup,
  setGroupTiming,
  moveQueueItem,
  SEND_QUEUE_MAX,
  type SendQueueItem,
} from "./sendQueue";

describe("sendQueue helpers", () => {
  const base = (over: Partial<SendQueueItem> = {}): SendQueueItem => ({
    id: over.id ?? "1",
    text: over.text ?? "a",
    timing: over.timing ?? "defer",
    mergeWithNext: over.mergeWithNext ?? false,
    webEnabled: false,
    ...over,
  });

  it("takeNextGroup merges same-timing chain", () => {
    const items = [
      base({ id: "1", text: "one", mergeWithNext: true }),
      base({ id: "2", text: "two", mergeWithNext: true }),
      base({ id: "3", text: "three" }),
    ];
    const got = takeNextGroup(items);
    expect(got?.group.map((g) => g.id)).toEqual(["1", "2", "3"]);
    expect(mergeGroupText(got!.group)).toBe("one\n\ntwo\n\nthree");
    expect(got?.rest).toEqual([]);
  });

  it("takeNextGroup stops at timing mismatch", () => {
    const items = [
      base({ id: "1", mergeWithNext: true, timing: "defer" }),
      base({ id: "2", timing: "inject", text: "inj" }),
    ];
    const got = takeNextGroup(items);
    expect(got?.group.map((g) => g.id)).toEqual(["1"]);
    expect(got?.rest.map((g) => g.id)).toEqual(["2"]);
  });

  it("setGroupTiming unifies merge group", () => {
    const items = [
      base({ id: "1", mergeWithNext: true, timing: "defer" }),
      base({ id: "2", timing: "defer" }),
    ];
    const next = setGroupTiming(items, 1, "inject");
    expect(next.every((x) => x.timing === "inject")).toBe(true);
  });

  it("moveQueueItem swaps neighbors", () => {
    const items = [base({ id: "a" }), base({ id: "b" }), base({ id: "c" })];
    expect(moveQueueItem(items, 1, -1).map((x) => x.id)).toEqual([
      "b",
      "a",
      "c",
    ]);
  });

  it("persists and loads per conversation", () => {
    const keyCid = "cid-test-queue";
    const items = [base({ id: "x", text: "hello", timing: "inject" })];
    saveSendQueue(keyCid, items);
    const loaded = loadSendQueue(keyCid);
    expect(loaded).toHaveLength(1);
    expect(loaded[0].text).toBe("hello");
    expect(loaded[0].timing).toBe("inject");
    expect(loaded[0].locked).toBe(false);
    localStorage.removeItem(`lorechat.sendQueue.v1.${keyCid}`);
  });

  it("exposes max constant", () => {
    expect(SEND_QUEUE_MAX).toBe(20);
  });
});
