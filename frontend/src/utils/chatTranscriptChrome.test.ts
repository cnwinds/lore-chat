import { describe, expect, it } from "vitest";
import { chatTranscriptChrome } from "./chatTranscriptChrome";

describe("chatTranscriptChrome", () => {
  it("keeps the centered welcome while history is loading", () => {
    expect(
      chatTranscriptChrome({
        loadingHistory: true,
        hasHistory: false,
        tipHasBody: false,
        streaming: false,
        timelineHasMore: true,
        loadingOlder: false,
      }),
    ).toEqual({
      showWelcome: true,
      showWelcomeLoading: true,
      showLoadOlderHint: false,
    });
  });

  it("shows welcome without loading copy when the thread is empty", () => {
    expect(
      chatTranscriptChrome({
        loadingHistory: false,
        hasHistory: false,
        tipHasBody: false,
        streaming: false,
        timelineHasMore: false,
        loadingOlder: false,
      }),
    ).toEqual({
      showWelcome: true,
      showWelcomeLoading: false,
      showLoadOlderHint: false,
    });
  });

  it("hides welcome once messages exist and allows older-hint", () => {
    expect(
      chatTranscriptChrome({
        loadingHistory: true,
        hasHistory: false,
        tipHasBody: true,
        streaming: false,
        timelineHasMore: true,
        loadingOlder: false,
      }),
    ).toEqual({
      showWelcome: false,
      showWelcomeLoading: false,
      showLoadOlderHint: true,
    });
  });
});
