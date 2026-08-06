import { describe, expect, it } from "vitest";
import {
  formatMessageTs,
  markToolBlockResolved,
  kbPathFromToolResult,
  expandMessagesForDisplay,
  timelineAwaitsUserAnswer,
  normalizeLoadedMessage,
  liveStreamingStatus,
} from "./chatMessage";
import type { ChatMessage } from "../api";

describe("formatMessageTs", () => {
  it("formats UTC instant as Beijing HH:mm", () => {
    const out = formatMessageTs("2026-07-12T06:30:00.000Z");
    expect(out).toBe("14:30");
  });

  it("returns empty for invalid", () => {
    expect(formatMessageTs("not-a-date")).toBe("");
  });
});

describe("markToolBlockResolved", () => {
  it("patches matching tool block in timeline", () => {
    const msgs: ChatMessage[] = [
      {
        role: "assistant",
        timeline: [
          {
            type: "tool",
            id: "t1",
            tool: "ask_user",
            label: "提问",
            ts: "2026-07-12T14:30:00.000Z",
            status: "running",
          },
        ],
      },
    ];
    const next = markToolBlockResolved(msgs, "t1", "选项 A");
    expect(next[0].timeline?.[0]).toMatchObject({
      choice_resolved: "选项 A",
    });
  });
});

describe("kbPathFromToolResult", () => {
  it("returns kb path from sources", () => {
    const path = kbPathFromToolResult({
      sources: [{ type: "kb", path: "foo/bar.md" }],
    });
    expect(path).toBe("foo/bar.md");
  });
});

describe("expandMessagesForDisplay", () => {
  it("splits assistant timeline around user_inject into user bubbles", () => {
    const msgs: ChatMessage[] = [
      { role: "user", text: "先问", id: "u0" },
      {
        role: "user",
        text: "补充",
        id: "u-inj",
        injected: true,
        client_message_id: "inject:inj1",
      },
      {
        role: "assistant",
        id: "a0",
        timeline: [
          {
            type: "tool",
            id: "t1",
            tool: "search_kb",
            label: "检索",
            ts: "t0",
            status: "done",
          },
          {
            type: "user_inject",
            inject_id: "inj1",
            ts: "t1",
            text: "补充",
            message_id: "u-inj",
          },
          { type: "text", ts: "t2", content: "结论" },
        ],
      },
    ];
    const rows = expandMessagesForDisplay(msgs);
    expect(rows.map((r) => r.message.role)).toEqual([
      "user",
      "assistant",
      "user",
      "assistant",
    ]);
    expect(rows[2].message).toMatchObject({
      role: "user",
      text: "补充",
      injected: true,
    });
    expect(rows[1].message.timeline?.map((b) => b.type)).toEqual(["tool"]);
    expect(rows[3].message.timeline?.map((b) => b.type)).toEqual(["text"]);
  });
});

describe("timelineAwaitsUserAnswer", () => {
  it("detects unanswered ask_user blocks", () => {
    expect(
      timelineAwaitsUserAnswer([
        {
          type: "tool",
          id: "t1",
          tool: "ask_user",
          label: "征询",
          ts: "t",
          status: "done",
          question_id: "q1",
          options: [{ id: "a", label: "A" }],
        },
      ]),
    ).toBe(true);
    expect(
      timelineAwaitsUserAnswer([
        {
          type: "tool",
          id: "t1",
          tool: "ask_user",
          label: "征询",
          ts: "t",
          status: "done",
          question_id: "q1",
          options: [{ id: "a", label: "A" }],
          choice_resolved: "A",
        },
      ]),
    ).toBe(false);
  });
});

describe("normalizeLoadedMessage", () => {
  it("marks stuck running tools as interrupted", () => {
    const msg = normalizeLoadedMessage({
      role: "assistant",
      timeline: [
        {
          type: "tool",
          id: "t1",
          tool: "sandbox_run",
          label: "run",
          ts: "t",
          status: "running",
        },
      ],
    });
    expect(msg.status).toBe("interrupted");
    expect(msg.timeline?.[0]).toMatchObject({
      status: "interrupted",
      summary: "连接中断，未完成",
    });
  });
});

describe("liveStreamingStatus", () => {
  it("shows latest sandbox progress on the control bar", () => {
    const msgs = [
      {
        role: "assistant" as const,
        timeline: [
          {
            type: "tool" as const,
            id: "t1",
            tool: "sandbox_run",
            label: "在沙箱执行命令",
            ts: "t",
            status: "running" as const,
            query: "python fetch.py",
            progress_log: ["$ python fetch.py", "top count: 500", "仍在运行… 90s"],
          },
        ],
      },
    ];
    expect(liveStreamingStatus(msgs, 0)).toBe("top count: 500");
  });
});
