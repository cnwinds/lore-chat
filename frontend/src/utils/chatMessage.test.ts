import { describe, expect, it } from "vitest";
import {
  formatMessageTs,
  markToolBlockResolved,
  kbPathFromToolResult,
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
