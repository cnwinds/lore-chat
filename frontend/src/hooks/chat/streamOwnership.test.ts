import { describe, it, expect } from "vitest";
import {
  createStreamOwnership,
  isStreamingForView,
  shouldProtectStreamingHistory,
} from "./streamOwnership";

describe("streamOwnership", () => {
  it("protects history only when msgs already belong to the streaming conversation", () => {
    const ownership = createStreamOwnership();
    ownership.streamingRef.current = true;
    ownership.streamConversationIdRef.current = "cid-a";
    ownership.msgsConversationIdRef.current = "cid-b";
    expect(shouldProtectStreamingHistory(ownership, "cid-a")).toBe(false);

    ownership.msgsConversationIdRef.current = "cid-a";
    expect(shouldProtectStreamingHistory(ownership, "cid-a")).toBe(true);
  });

  it("scopes streaming UI to the viewed conversation", () => {
    expect(isStreamingForView(true, "cid-a", "cid-b")).toBe(false);
    expect(isStreamingForView(true, "cid-a", "cid-a")).toBe(true);
    expect(isStreamingForView(true, null, null)).toBe(true);
    expect(isStreamingForView(false, "cid-a", "cid-a")).toBe(false);
  });
});
