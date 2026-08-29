import { describe, expect, it } from "vitest";
import {
  formatMessageTs,
  markToolBlockResolved,
  kbPathFromToolResult,
  expandMessagesForDisplay,
  timelineAwaitsUserAnswer,
  normalizeLoadedMessage,
  canRetryAssistantReply,
  findPrecedingUserForRetry,
} from "./chatMessage";
import type { ChatMessage } from "../api";

describe("formatMessageTs", () => {
  it("formats UTC instant as Beijing HH:mm on same calendar day", () => {
    const now = new Date("2026-07-12T10:00:00+08:00");
    const out = formatMessageTs("2026-07-12T06:30:00.000Z", now);
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

  it("keeps running tools when server turn is still active", () => {
    const msg = normalizeLoadedMessage(
      {
        role: "assistant",
        timeline: [
          {
            type: "tool",
            id: "t1",
            tool: "sandbox_run",
            label: "run",
            ts: "2026-08-29T22:25:00+08:00",
            status: "running",
          },
        ],
      },
      { activeTurnRunning: true },
    );
    expect(msg.status).toBeUndefined();
    expect(msg.timeline?.[0]).toMatchObject({
      status: "running",
      started_at_ms: Date.parse("2026-08-29T22:25:00+08:00"),
    });
  });

  it("stamps nested parallel children when turn is active", () => {
    const iso = "2026-08-29T22:25:00+08:00";
    const msg = normalizeLoadedMessage(
      {
        role: "assistant",
        timeline: [
          {
            type: "parallel",
            batch_id: "b1",
            ts: iso,
            children: [
              {
                type: "tool",
                id: "t1",
                tool: "sandbox_run",
                label: "run",
                ts: iso,
                status: "running",
              },
            ],
          },
        ],
      },
      { activeTurnRunning: true },
    );
    const batch = msg.timeline?.[0];
    expect(batch?.type).toBe("parallel");
    if (batch?.type === "parallel") {
      expect(batch.children[0]).toMatchObject({
        status: "running",
        started_at_ms: Date.parse(iso),
      });
    }
  });

  it("leaves started_at_ms unset when active-turn ts is unparsable", () => {
    const msg = normalizeLoadedMessage(
      {
        role: "assistant",
        timeline: [
          {
            type: "tool",
            id: "t1",
            tool: "sandbox_run",
            label: "run",
            ts: "not-a-date",
            status: "running",
          },
        ],
      },
      { activeTurnRunning: true },
    );
    const tool = msg.timeline?.[0];
    expect(tool?.type).toBe("tool");
    if (tool?.type === "tool") {
      expect(tool.started_at_ms).toBeUndefined();
      expect(tool.status).toBe("running");
    }
  });
});

describe("canRetryAssistantReply", () => {
  it("allows error and interrupted assistant messages", () => {
    expect(
      canRetryAssistantReply({ role: "assistant", text: "错误：超时", status: "error" }),
    ).toBe(true);
    expect(
      canRetryAssistantReply({ role: "assistant", text: "半截", status: "interrupted" }),
    ).toBe(true);
    expect(
      canRetryAssistantReply({ role: "assistant", text: "错误：网关失败" }),
    ).toBe(true);
  });

  it("rejects complete replies and pending ask_user", () => {
    expect(
      canRetryAssistantReply({ role: "assistant", text: "正常回复", status: "complete" }),
    ).toBe(false);
    expect(
      canRetryAssistantReply({
        role: "assistant",
        status: "interrupted",
        timeline: [
          {
            type: "tool",
            id: "t1",
            tool: "ask_user",
            label: "提问",
            ts: "t",
            status: "done",
            question_id: "q1",
            options: [{ id: "a", label: "A" }],
          },
        ],
      }),
    ).toBe(false);
  });
});

describe("findPrecedingUserForRetry", () => {
  it("returns the turn user and stops at previous assistant", () => {
    const msgs: ChatMessage[] = [
      { role: "user", text: "旧问" },
      { role: "assistant", text: "旧答" },
      { role: "user", text: "新问", attachments: ["a.png"] },
      { role: "assistant", text: "错误：失败", status: "error" },
    ];
    expect(findPrecedingUserForRetry(msgs, 3)?.text).toBe("新问");
  });

  it("skips injected user messages", () => {
    const msgs: ChatMessage[] = [
      { role: "user", text: "主问" },
      { role: "user", text: "插入", injected: true, client_message_id: "inject:1" },
      { role: "assistant", text: "错误：x", status: "error" },
    ];
    expect(findPrecedingUserForRetry(msgs, 2)?.text).toBe("主问");
  });
});
