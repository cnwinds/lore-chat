import { describe, expect, it, vi } from "vitest";
import {
  buildObservationEnd,
  fetchConversationWithRetry,
  needsServerReconcile,
  shouldReloadConversation,
  toStreamEndPayload,
} from "./turnReconcile";

describe("turnReconcile", () => {
  it("treats incomplete non-aborted observation as needing reconcile", () => {
    const info = buildObservationEnd({
      completed: false,
      serverStreamError: false,
      aborted: false,
      awaitingUser: false,
    });
    expect(needsServerReconcile(info)).toBe(true);
    expect(shouldReloadConversation(info)).toBe("reconcile");
    expect(toStreamEndPayload(info).detached).toBe(true);
  });

  it("maps completed turn to full reload", () => {
    const info = buildObservationEnd({
      completed: true,
      serverStreamError: false,
      aborted: false,
      awaitingUser: false,
    });
    expect(shouldReloadConversation(info)).toBe("full");
  });

  it("retries fetch until success", async () => {
    const fetchConv = vi
      .fn()
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce({
        id: "cid-1",
        title: "t",
        created_at: "",
        updated_at: "",
        message_count: 0,
        summarized: false,
        summary_path: null,
        messages: [],
        active_turn: { turn_id: "t1", status: "running", started_at: null },
      });
    const conv = await fetchConversationWithRetry("cid-1", fetchConv, [0, 0]);
    expect(conv?.active_turn?.status).toBe("running");
    expect(fetchConv).toHaveBeenCalledTimes(2);
  });
});
