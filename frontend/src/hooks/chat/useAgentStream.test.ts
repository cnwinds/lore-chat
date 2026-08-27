import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useAgentStream } from "./useAgentStream";
import { createStreamOwnership } from "./streamOwnership";
import * as api from "../../api";
import type { ChatMessage, DocContextItem } from "../../api";

vi.mock("../../api", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../../api")>();
  return {
    ...mod,
    chatStream: vi.fn(),
    observeActiveTurnStream: vi.fn(),
    createConversation: vi.fn().mockResolvedValue({ id: "new-cid" }),
    getConversation: vi.fn().mockResolvedValue({
      id: "cid-1",
      title: "t",
      created_at: "",
      updated_at: "",
      message_count: 0,
      summarized: false,
      summary_path: null,
      messages: [],
    }),
  };
});

function makeSetMsgs(initial: ChatMessage[]) {
  let current = initial;
  const setMsgs = vi.fn(
    (updater: ChatMessage[] | ((prev: ChatMessage[]) => ChatMessage[])) => {
      current =
        typeof updater === "function"
          ? (updater as (prev: ChatMessage[]) => ChatMessage[])(current)
          : updater;
      return current;
    },
  );
  return { setMsgs, getCurrent: () => current };
}

function baseOptions(overrides: Partial<Parameters<typeof useAgentStream>[0]> = {}) {
  const { setMsgs } = makeSetMsgs([]);
  return {
    conversationId: "cid-1",
    previewPath: null,
    webEnabled: false,
    docContextItems: [] as DocContextItem[],
    primaryDocPath: null,
    msgs: [] as ChatMessage[],
    setMsgs,
    setSummarized: vi.fn(),
    setSummaryPath: vi.fn(),
    conversationIdRef: { current: "cid-1" as string | null },
    skipLoadRef: { current: null as string | null },
    streamOwnership: createStreamOwnership(),
    stickToBottomRef: { current: true },
    onSidebarRefresh: vi.fn(),
    onKbChanged: vi.fn(),
    onFirstQuestionTitle: vi.fn(),
    onConversationCreated: vi.fn(),
    ...overrides,
  };
}

describe("useAgentStream", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.createConversation).mockResolvedValue({ id: "new-cid" });
    vi.mocked(api.getConversation).mockResolvedValue({
      id: "cid-1",
      title: "t",
      created_at: "",
      updated_at: "",
      message_count: 0,
      summarized: false,
      summary_path: null,
      messages: [],
    });
    vi.mocked(api.chatStream).mockImplementation(async function* () {
      yield { event: "done", data: { sources: [] } };
    });
    vi.mocked(api.observeActiveTurnStream).mockImplementation(async function* () {
      yield { event: "done", data: { sources: [] } };
    });
  });

  it("sets streaming false after completion and clears skipLoadRef/streamingRef", async () => {
    const options = baseOptions();
    const { result } = renderHook(() => useAgentStream(options));

    await act(async () => {
      await result.current.runAgentStream("hello");
    });

    expect(result.current.streaming).toBe(false);
    expect(options.streamOwnership.streamingRef.current).toBe(false);
    expect(options.streamOwnership.streamConversationIdRef.current).toBeNull();
    expect(options.skipLoadRef.current).toBeNull();
  });

  it("appends user + assistant messages and patches the LAST message with timeline/sources on done", async () => {
    vi.mocked(api.chatStream).mockImplementation(async function* () {
      yield {
        event: "tool_start",
        data: { id: "t1", tool: "search_kb", ts: "2026-01-01T00:00:00.000Z" },
      };
      yield {
        event: "done",
        data: { sources: [{ type: "kb", path: "a.md" }], total_duration_ms: 42 },
      };
    });
    vi.mocked(api.getConversation).mockResolvedValue({
      id: "cid-1",
      title: "t",
      created_at: "",
      updated_at: "",
      message_count: 2,
      summarized: false,
      summary_path: null,
      messages: [
        { id: "u1", role: "user", text: "hi there", ts: "2026-01-01T00:00:00.000Z" },
        {
          id: "a1",
          role: "assistant",
          ts: "2026-01-01T00:00:00.000Z",
          timeline: [
            {
              type: "tool",
              id: "t1",
              tool: "search_kb",
              label: "检索本地知识库",
              ts: "2026-01-01T00:00:00.000Z",
              status: "running",
            },
          ],
          sources: [{ type: "kb", path: "a.md" }],
          total_duration_ms: 42,
        },
      ],
    });
    const { setMsgs, getCurrent } = makeSetMsgs([]);
    const options = baseOptions({ setMsgs });
    const { result } = renderHook(() => useAgentStream(options));

    await act(async () => {
      await result.current.runAgentStream("hi there");
    });

    const msgs = getCurrent();
    expect(msgs).toHaveLength(2);
    expect(msgs[0]).toMatchObject({ role: "user", text: "hi there" });
    // patchAssistant must always target the LAST array element, never msgs[0]
    const assistant = msgs[msgs.length - 1];
    expect(assistant.role).toBe("assistant");
    expect(assistant.timeline?.[0]).toMatchObject({ tool: "search_kb" });
    expect(assistant.sources).toEqual([{ type: "kb", path: "a.md" }]);
    expect(assistant.total_duration_ms).toBe(42);
  });

  it("uses userDisplayText for the user bubble while sending apiText to chatStream (continue flow)", async () => {
    vi.mocked(api.getConversation).mockResolvedValue({
      id: "cid-1",
      title: "t",
      created_at: "",
      updated_at: "",
      message_count: 4,
      summarized: false,
      summary_path: null,
      messages: [
        { id: "u0", role: "user", text: "prior question", ts: "2026-01-01T00:00:00.000Z" },
        { id: "a0", role: "assistant", text: "prior answer", ts: "2026-01-01T00:00:00.000Z" },
        { id: "u1", role: "user", text: "选项 A", ts: "2026-01-01T00:00:01.000Z" },
        { id: "a1", role: "assistant", ts: "2026-01-01T00:00:01.000Z", timeline: [], sources: [] },
      ],
    });
    const { setMsgs, getCurrent } = makeSetMsgs([
      { role: "user", text: "prior question" },
      { role: "assistant", text: "prior answer" },
    ]);
    const options = baseOptions({
      setMsgs,
      msgs: [
        { role: "user", text: "prior question" },
        { role: "assistant", text: "prior answer" },
      ],
    });
    const { result } = renderHook(() => useAgentStream(options));

    await act(async () => {
      await result.current.runAgentStream("continue_prompt_text", "选项 A");
    });

    expect(vi.mocked(api.chatStream)).toHaveBeenCalledWith(
      "continue_prompt_text",
      expect.objectContaining({
        conversationId: "cid-1",
        webEnabled: false,
      }),
    );
    const msgs = getCurrent();
    // the new user bubble (not the last one, since assistant is appended after) must show the display text
    expect(msgs[2]).toMatchObject({ role: "user", text: "选项 A" });
  });

  it("shows error when reconcile cannot reach server after stream throws", async () => {
    vi.mocked(api.chatStream).mockImplementation(async function* () {
      yield* [];
      throw new Error("boom");
    });
    vi.mocked(api.getConversation).mockRejectedValue(new Error("offline"));
    const { setMsgs, getCurrent } = makeSetMsgs([]);
    const options = baseOptions({ setMsgs });
    const { result } = renderHook(() => useAgentStream(options));

    await act(async () => {
      await result.current.runAgentStream("hello");
    });

    const msgs = getCurrent();
    const assistant = msgs[msgs.length - 1];
    expect(assistant.text).toContain("无法同步服务器状态");
    expect(assistant.status).toBe("error");
    expect(result.current.streaming).toBe(false);
  });

  it("resumes observation when server turn is still running after stream throws", async () => {
    vi.mocked(api.chatStream).mockImplementation(async function* () {
      yield* [];
      throw new Error("boom");
    });
    vi.mocked(api.getConversation).mockResolvedValue({
      id: "cid-1",
      title: "t",
      created_at: "",
      updated_at: "",
      message_count: 1,
      summarized: false,
      summary_path: null,
      messages: [
        {
          role: "user",
          text: "hello",
          ts: "2026-01-01T00:00:00.000Z",
        },
      ],
      active_turn: {
        turn_id: "t1",
        status: "running",
        started_at: "2026-01-01T00:00:00.000Z",
      },
    });
    const { setMsgs, getCurrent } = makeSetMsgs([]);
    const options = baseOptions({ setMsgs });
    const { result } = renderHook(() => useAgentStream(options));

    await act(async () => {
      await result.current.runAgentStream("hello");
    });

    expect(vi.mocked(api.observeActiveTurnStream)).toHaveBeenCalledWith(
      "cid-1",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(getCurrent().some((m) => (m.text || "").startsWith("错误"))).toBe(
      false,
    );
    expect(result.current.streaming).toBe(false);
  });

  it("ensureConversationId creates a conversation and marks skipLoadRef when none exists", async () => {
    const options = baseOptions({
      conversationId: null,
      conversationIdRef: { current: null },
      onConversationCreated: vi.fn(),
    });
    const { result } = renderHook(() => useAgentStream(options));

    let cid: string | undefined;
    await act(async () => {
      cid = await result.current.ensureConversationId();
    });

    expect(cid).toBe("new-cid");
    expect(options.skipLoadRef.current).toBe("new-cid");
    expect(options.conversationIdRef.current).toBe("new-cid");
    expect(options.onConversationCreated).toHaveBeenCalledWith("new-cid");
  });

  it("keeps observing when conversationId is assigned mid-stream (null → id)", async () => {
    let releaseStream: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      releaseStream = resolve;
    });
    let sawAbort = false;
    let streamFullyConsumed = false;
    vi.mocked(api.chatStream).mockImplementation(async function* (_text, opts) {
      const signal = opts?.signal;
      const onAbort = () => {
        sawAbort = true;
      };
      signal?.addEventListener("abort", onAbort);
      try {
        await gate;
        if (signal?.aborted) {
          const err = new Error("Aborted");
          err.name = "AbortError";
          throw err;
        }
        yield {
          event: "tool_start",
          data: { id: "t1", tool: "search_kb", ts: "2026-01-01T00:00:00.000Z" },
        };
        yield { event: "done", data: { sources: [] } };
        streamFullyConsumed = true;
      } finally {
        signal?.removeEventListener("abort", onAbort);
      }
    });

    const conversationIdRef = { current: null as string | null };
    const { setMsgs } = makeSetMsgs([]);
    const options = baseOptions({
      conversationId: null,
      conversationIdRef,
      setMsgs,
      onConversationCreated: (id) => {
        conversationIdRef.current = id;
      },
    });

    const { result, rerender } = renderHook(
      (props) => useAgentStream(props),
      { initialProps: options },
    );

    let run!: Promise<boolean>;
    await act(async () => {
      run = result.current.runAgentStream("hello new chat");
      await Promise.resolve();
      await Promise.resolve();
    });

    // Simulate parent assigning the new conversation id (as onConversationCreated does).
    rerender({ ...options, conversationId: "new-cid" });
    await act(async () => {
      await Promise.resolve();
    });

    releaseStream?.();
    await act(async () => {
      await run;
    });

    expect(sawAbort).toBe(false);
    expect(streamFullyConsumed).toBe(true);
    expect(result.current.streaming).toBe(false);
  });

  it("ignores concurrent runAgentStream calls while already streaming", async () => {
    let resolveStream: (() => void) | undefined;
    vi.mocked(api.chatStream).mockImplementation(async function* () {
      await new Promise<void>((resolve) => {
        resolveStream = resolve;
      });
      yield { event: "done", data: { sources: [] } };
    });
    const options = baseOptions();
    const { result } = renderHook(() => useAgentStream(options));

    let firstCall!: Promise<boolean>;
    await act(async () => {
      firstCall = result.current.runAgentStream("first");
      // let the setStreaming(true) update flush so result.current reflects it
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current.streaming).toBe(true);

    await act(async () => {
      const second = await result.current.runAgentStream("second");
      expect(second).toBe(false);
    });
    expect(vi.mocked(api.chatStream)).toHaveBeenCalledTimes(1);

    resolveStream?.();
    await act(async () => {
      await firstCall;
    });
    expect(result.current.streaming).toBe(false);
  });

  it("does not paint stream events onto another conversation after switch", async () => {
    let pushEvent: ((ev: { event: string; data: Record<string, unknown> }) => void) | undefined;
    let finishGate: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      finishGate = resolve;
    });
    vi.mocked(api.chatStream).mockImplementation(async function* (_text, opts) {
      const queue: Array<{ event: string; data: Record<string, unknown> }> = [];
      let waiting: (() => void) | undefined;
      pushEvent = (ev) => {
        queue.push(ev);
        waiting?.();
      };
      const signal = opts?.signal;
      while (true) {
        if (signal?.aborted) {
          const err = new Error("Aborted");
          err.name = "AbortError";
          throw err;
        }
        if (queue.length === 0) {
          await new Promise<void>((resolve) => {
            waiting = resolve;
          });
          continue;
        }
        const next = queue.shift()!;
        if (next.event === "__end__") break;
        yield next as never;
      }
      await gate;
    });

    const conversationIdRef = { current: "cid-a" as string | null };
    const { setMsgs, getCurrent } = makeSetMsgs([]);
    const onStreamEnd = vi.fn();
    const options = baseOptions({
      conversationId: "cid-a",
      conversationIdRef,
      setMsgs,
      onStreamEnd,
    });
    const { result } = renderHook(() => useAgentStream(options));

    let run!: Promise<boolean>;
    await act(async () => {
      run = result.current.runAgentStream("hello");
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current.streamingForView).toBe(true);
    expect(getCurrent().length).toBeGreaterThanOrEqual(2);

    // Parent updated the viewed-conversation ref before abort settles.
    conversationIdRef.current = "cid-b";
    const snapshot = structuredClone(getCurrent());
    await act(async () => {
      pushEvent?.({
        event: "tool_start",
        data: { id: "t1", tool: "search_kb", ts: "2026-01-01T00:00:00.000Z" },
      });
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(getCurrent()).toEqual(snapshot);

    await act(async () => {
      pushEvent?.({ event: "__end__", data: {} });
      finishGate?.();
      await run;
    });

    // Switched away before end — do not drive the other chat's outbound queue.
    expect(onStreamEnd).not.toHaveBeenCalled();
  });

  it("does not apply model_selected from another conversation onto loaded history", async () => {
    let pushEvent: ((ev: { event: string; data: Record<string, unknown> }) => void) | undefined;
    let finishGate: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      finishGate = resolve;
    });
    vi.mocked(api.chatStream).mockImplementation(async function* (_text, opts) {
      const queue: Array<{ event: string; data: Record<string, unknown> }> = [];
      let waiting: (() => void) | undefined;
      pushEvent = (ev) => {
        queue.push(ev);
        waiting?.();
      };
      const signal = opts?.signal;
      while (true) {
        if (signal?.aborted) {
          const err = new Error("Aborted");
          err.name = "AbortError";
          throw err;
        }
        if (queue.length === 0) {
          await new Promise<void>((resolve) => {
            waiting = resolve;
          });
          continue;
        }
        const next = queue.shift()!;
        if (next.event === "__end__") break;
        yield next as never;
      }
      await gate;
    });

    const conversationIdRef = { current: "cid-b" as string | null };
    const ownership = createStreamOwnership();
    const { setMsgs, getCurrent } = makeSetMsgs([]);
    const options = baseOptions({
      conversationId: "cid-b",
      conversationIdRef,
      setMsgs,
      streamOwnership: ownership,
    });
    const { result } = renderHook(() => useAgentStream(options));

    let run!: Promise<boolean>;
    await act(async () => {
      run = result.current.runAgentStream("from-b");
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(ownership.msgsConversationIdRef.current).toBe("cid-b");

    // View switched to A and history loaded; conversationIdRef still stale as B.
    setMsgs([
      { role: "user", text: "from-a", ts: "2026-01-01T00:00:00.000Z" },
      {
        role: "assistant",
        text: "reply-a",
        model_name: "model-a",
        ts: "2026-01-01T00:00:01.000Z",
      },
    ]);
    ownership.msgsConversationIdRef.current = "cid-a";

    await act(async () => {
      pushEvent?.({
        event: "model_selected",
        data: { model: "model-b", failover: false },
      });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(getCurrent()[1]).toMatchObject({
      role: "assistant",
      model_name: "model-a",
    });

    await act(async () => {
      pushEvent?.({ event: "__end__", data: {} });
      finishGate?.();
      await run;
    });
  });

  it("does not reload finished stream history onto another conversation's msgs", async () => {
    let resolveReload:
      | ((value: Awaited<ReturnType<typeof api.getConversation>>) => void)
      | undefined;
    vi.mocked(api.chatStream).mockImplementation(async function* () {
      yield { event: "done", data: { sources: [] } };
    });
    vi.mocked(api.getConversation).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveReload = resolve;
        }),
    );

    const conversationIdRef = { current: "cid-b" as string | null };
    const ownership = createStreamOwnership();
    const { setMsgs, getCurrent } = makeSetMsgs([]);
    const options = baseOptions({
      conversationId: "cid-b",
      conversationIdRef,
      setMsgs,
      streamOwnership: ownership,
    });
    const { result } = renderHook(() => useAgentStream(options));

    let run!: Promise<boolean>;
    await act(async () => {
      run = result.current.runAgentStream("from-b");
      await Promise.resolve();
      await Promise.resolve();
    });

    setMsgs([
      { role: "user", text: "from-a", ts: "2026-01-01T00:00:00.000Z" },
      {
        role: "assistant",
        text: "reply-a",
        model_name: "model-a",
        ts: "2026-01-01T00:00:01.000Z",
      },
    ]);
    ownership.msgsConversationIdRef.current = "cid-a";
    conversationIdRef.current = "cid-a";

    await act(async () => {
      await run;
    });

    resolveReload?.({
      id: "cid-b",
      title: "b",
      created_at: "",
      updated_at: "",
      message_count: 1,
      summarized: false,
      summary_path: null,
      messages: [
        {
          role: "user",
          text: "from-b",
          ts: "2026-01-01T00:00:00.000Z",
        },
        {
          role: "assistant",
          text: "reply-b",
          model_name: "model-b",
          ts: "2026-01-01T00:00:01.000Z",
        },
      ],
    });

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(getCurrent()[1]).toMatchObject({
      role: "assistant",
      model_name: "model-a",
      text: "reply-a",
    });
  });

  it("scopes streamingForView to the conversation that owns the stream", async () => {
    let resolveStream: (() => void) | undefined;
    vi.mocked(api.chatStream).mockImplementation(async function* () {
      await new Promise<void>((resolve) => {
        resolveStream = resolve;
      });
      yield { event: "done", data: { sources: [] } };
    });
    const options = baseOptions({ conversationId: "cid-a" });
    const { result, rerender } = renderHook(
      (props) => useAgentStream(props),
      { initialProps: options },
    );

    let run!: Promise<boolean>;
    await act(async () => {
      run = result.current.runAgentStream("hello");
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(result.current.streamingForView).toBe(true);

    rerender({ ...options, conversationId: "cid-b" });
    await act(async () => {
      await Promise.resolve();
    });
    // Switch detaches and clears ownership immediately.
    expect(result.current.streamingForView).toBe(false);
    expect(result.current.streaming).toBe(false);

    resolveStream?.();
    await act(async () => {
      await run;
    });
  });

  it("detached finishObservation must not clear a newer stream's ownership", async () => {
    // Repro: A streaming → switch to B (abort A, clear ownership) → start B →
    // A's finally/finishObservation must not wipe B's claim (cross-talk root).
    let releaseA: (() => void) | undefined;
    const gateA = new Promise<void>((resolve) => {
      releaseA = resolve;
    });
    let releaseB: (() => void) | undefined;
    const gateB = new Promise<void>((resolve) => {
      releaseB = resolve;
    });
    let call = 0;
    vi.mocked(api.chatStream).mockImplementation(async function* (_text, opts) {
      const n = ++call;
      const signal = opts?.signal;
      const gate = n === 1 ? gateA : gateB;
      await gate;
      if (signal?.aborted) {
        const err = new Error("Aborted");
        err.name = "AbortError";
        throw err;
      }
      yield { event: "done", data: { sources: [] } };
    });

    const conversationIdRef = { current: "cid-a" as string | null };
    const ownership = createStreamOwnership();
    const optionsA = baseOptions({
      conversationId: "cid-a",
      conversationIdRef,
      streamOwnership: ownership,
    });
    const { result, rerender } = renderHook(
      (props) => useAgentStream(props),
      { initialProps: optionsA },
    );

    let runA!: Promise<boolean>;
    await act(async () => {
      runA = result.current.runAgentStream("from-a");
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(ownership.streamingRef.current).toBe(true);
    expect(ownership.streamConversationIdRef.current).toBe("cid-a");

    conversationIdRef.current = "cid-b";
    const optionsB = {
      ...optionsA,
      conversationId: "cid-b",
      conversationIdRef,
      streamOwnership: ownership,
    };
    rerender(optionsB);
    await act(async () => {
      await Promise.resolve();
    });
    expect(ownership.streamingRef.current).toBe(false);

    let runB!: Promise<boolean>;
    await act(async () => {
      runB = result.current.runAgentStream("from-b");
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(ownership.streamConversationIdRef.current).toBe("cid-b");
    expect(ownership.streamingRef.current).toBe(true);

    releaseA?.();
    await act(async () => {
      await runA;
    });
    expect(ownership.streamConversationIdRef.current).toBe("cid-b");
    expect(ownership.streamingRef.current).toBe(true);

    releaseB?.();
    await act(async () => {
      await runB;
    });
    expect(ownership.streamingRef.current).toBe(false);
  });

  it("detached finishObservation must not fire onStreamEnd for another conversation", async () => {
    let releaseA: (() => void) | undefined;
    const gateA = new Promise<void>((resolve) => {
      releaseA = resolve;
    });
    vi.mocked(api.chatStream).mockImplementation(async function* (_text, opts) {
      const signal = opts?.signal;
      await gateA;
      if (signal?.aborted) {
        const err = new Error("Aborted");
        err.name = "AbortError";
        throw err;
      }
      yield { event: "done", data: { sources: [] } };
    });

    const conversationIdRef = { current: "cid-a" as string | null };
    const onStreamEnd = vi.fn();
    const options = baseOptions({
      conversationId: "cid-a",
      conversationIdRef,
      onStreamEnd,
    });
    const { result, rerender } = renderHook(
      (props) => useAgentStream(props),
      { initialProps: options },
    );

    let runA!: Promise<boolean>;
    await act(async () => {
      runA = result.current.runAgentStream("from-a");
      await Promise.resolve();
      await Promise.resolve();
    });

    conversationIdRef.current = "cid-b";
    rerender({
      ...options,
      conversationId: "cid-b",
      conversationIdRef,
      onStreamEnd,
    });
    await act(async () => {
      await Promise.resolve();
    });

    releaseA?.();
    await act(async () => {
      await runA;
    });

    expect(onStreamEnd).not.toHaveBeenCalled();
  });

  it("does not append a new send onto another conversation's leftover messages", async () => {
    let resolveStream: (() => void) | undefined;
    vi.mocked(api.chatStream).mockImplementation(async function* () {
      await new Promise<void>((resolve) => {
        resolveStream = resolve;
      });
      yield { event: "done", data: { sources: [] } };
    });

    const { setMsgs, getCurrent } = makeSetMsgs([
      { role: "user", text: "from-a", ts: "2026-01-01T00:00:00.000Z" },
      { role: "assistant", text: "reply-a", ts: "2026-01-01T00:00:01.000Z" },
    ]);
    const ownership = createStreamOwnership();
    ownership.msgsConversationIdRef.current = "cid-a";
    const conversationIdRef = { current: "cid-b" as string | null };
    const options = baseOptions({
      conversationId: "cid-b",
      conversationIdRef,
      setMsgs,
      streamOwnership: ownership,
    });
    const { result } = renderHook(() => useAgentStream(options));

    let run!: Promise<boolean>;
    await act(async () => {
      run = result.current.runAgentStream("from-b");
      await Promise.resolve();
      await Promise.resolve();
    });

    const texts = getCurrent().map((m) => m.text);
    expect(texts).not.toContain("from-a");
    expect(texts).not.toContain("reply-a");
    expect(texts[0]).toBe("from-b");
    expect(ownership.msgsConversationIdRef.current).toBe("cid-b");

    resolveStream?.();
    await act(async () => {
      await run;
    });
  });
});
