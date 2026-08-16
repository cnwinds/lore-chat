import { describe, expect, it } from "vitest";
import {
  reduceStreamEvent,
  type StreamReduceState,
} from "./agentStreamProjection";
import type { ChatMessage } from "../types/chat";

function baseState(overrides: Partial<StreamReduceState> = {}): StreamReduceState {
  const assistant: ChatMessage = {
    id: "a1",
    role: "assistant",
    text: "",
    timeline: [],
  };
  return {
    streamFailed: false,
    awaitingUser: false,
    serverTimeline: false,
    assistant,
    ...overrides,
  };
}

describe("reduceStreamEvent serverTimeline + deltas", () => {
  it("applies think_delta after timeline_state so UI keeps streaming without full snapshots", () => {
    let state = baseState();
    let result = reduceStreamEvent(state, "timeline_state", {
      timeline: [
        {
          type: "tool",
          id: "t1",
          tool: "fetch_url",
          label: "fetch",
          ts: "2026-01-01T00:00:00Z",
          status: "done",
          summary: "ok",
          content: "X".repeat(100),
        },
      ],
      assistant_text: "",
    });
    state = result.state;
    expect(state.serverTimeline).toBe(true);

    result = reduceStreamEvent(state, "think_delta", {
      delta: "hello",
      ts: "2026-01-01T00:00:01Z",
    });
    const timeline = result.state.assistant.timeline ?? [];
    const think = timeline.find((b) => b.type === "think");
    expect(think).toMatchObject({ type: "think", content: "hello" });

    result = reduceStreamEvent(result.state, "think_delta", {
      delta: " world",
      ts: "2026-01-01T00:00:02Z",
    });
    const think2 = (result.state.assistant.timeline ?? []).find((b) => b.type === "think");
    expect(think2).toMatchObject({ type: "think", content: "hello world" });
  });

  it("appends text_delta to assistant.text under serverTimeline", () => {
    let state = baseState({ serverTimeline: true });
    let result = reduceStreamEvent(state, "text_delta", {
      delta: "Hi",
      ts: "2026-01-01T00:00:00Z",
    });
    expect(result.state.assistant.text).toBe("Hi");
    result = reduceStreamEvent(result.state, "text_delta", {
      delta: "!",
      ts: "2026-01-01T00:00:01Z",
    });
    expect(result.state.assistant.text).toBe("Hi!");
  });

  it("does not append text_delta to assistant.text before serverTimeline", () => {
    const state = baseState({ serverTimeline: false });
    const result = reduceStreamEvent(state, "text_delta", {
      delta: "Hi",
      ts: "2026-01-01T00:00:00Z",
    });
    expect(result.state.assistant.text).toBe("");
    const textBlock = (result.state.assistant.timeline ?? []).find((b) => b.type === "text");
    expect(textBlock).toMatchObject({ type: "text", content: "Hi" });
  });

  it("applies tool_progress after timeline_state", () => {
    let state = baseState();
    let result = reduceStreamEvent(state, "timeline_state", {
      timeline: [
        {
          type: "tool",
          id: "t1",
          tool: "sandbox_run",
          label: "run",
          ts: "2026-01-01T00:00:00Z",
          status: "running",
        },
      ],
      assistant_text: "",
    });
    state = result.state;
    expect(state.serverTimeline).toBe(true);

    result = reduceStreamEvent(state, "tool_progress", {
      id: "t1",
      tool: "sandbox_run",
      message: "step 1",
    });
    const tool = (result.state.assistant.timeline ?? []).find(
      (b) => b.type === "tool" && b.id === "t1",
    );
    expect(tool).toMatchObject({
      type: "tool",
      id: "t1",
      summary: "step 1",
      progress_log: ["step 1"],
    });
  });
});
