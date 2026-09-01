import { describe, expect, it, vi } from "vitest";
import type { ActiveTurnStatus } from "../../api";
import {
  buildObservationEnd,
  fetchActiveTurnStatusWithRetry,
  isActiveTurnOrphaned,
  isActiveTurnRunning,
  needsServerReconcile,
  RECONCILE_DELAYS_MS,
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

  it("maps network unreachable to detached stream-end (not content failure)", () => {
    const info = buildObservationEnd({
      completed: false,
      serverStreamError: false,
      aborted: false,
      awaitingUser: false,
    });
    const payload = toStreamEndPayload(info, { networkUnreachable: true });
    expect(payload.failed).toBe(false);
    expect(payload.detached).toBe(true);
  });

  it("uses an extended probe window for mobile radio wake", () => {
    expect(RECONCILE_DELAYS_MS.length).toBeGreaterThanOrEqual(5);
    expect(RECONCILE_DELAYS_MS[RECONCILE_DELAYS_MS.length - 1]).toBeGreaterThanOrEqual(
      8000,
    );
  });

  it("retries active turn status until success", async () => {
    const running: ActiveTurnStatus = {
      conversation_id: "cid-1",
      turn_id: "t1",
      status: "running",
      started_at: null,
      last_seq: 3,
      observable: true,
    };
    const fetchStatus = vi
      .fn()
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce(running);
    const status = await fetchActiveTurnStatusWithRetry(
      "cid-1",
      fetchStatus,
      [0, 0],
    );
    expect(status?.status).toBe("running");
    expect(isActiveTurnRunning(status!)).toBe(true);
    expect(fetchStatus).toHaveBeenCalledTimes(2);
  });

  it("detects orphaned turn without observable memory task", () => {
    const orphaned: ActiveTurnStatus = {
      conversation_id: "cid-1",
      turn_id: "t1",
      status: "orphaned",
      started_at: null,
      last_seq: null,
      observable: false,
    };
    expect(isActiveTurnOrphaned(orphaned)).toBe(true);
    expect(isActiveTurnRunning(orphaned)).toBe(false);
  });
});
