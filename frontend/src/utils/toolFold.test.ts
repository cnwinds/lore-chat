import { describe, expect, it } from "vitest";
import type { TimelineBlock } from "../types/chat";
import { toolBlockDefaultOpen } from "./toolFold";

function tool(
  partial: Partial<Extract<TimelineBlock, { type: "tool" }>> &
    Pick<Extract<TimelineBlock, { type: "tool" }>, "tool">,
): Extract<TimelineBlock, { type: "tool" }> {
  return {
    type: "tool",
    id: partial.id ?? "t1",
    label: partial.label ?? partial.tool,
    ts: partial.ts ?? "2026-09-08T00:00:00Z",
    status: partial.status ?? "done",
    ...partial,
  };
}

describe("toolBlockDefaultOpen", () => {
  it("collapses sandbox, search, and generated images unless the user expands them", () => {
    expect(
      toolBlockDefaultOpen(
        tool({
          tool: "sandbox_run",
          query: "python --version",
          progress_log: ["Python 3.12.0"],
        }),
      ),
    ).toBe(false);
    expect(
      toolBlockDefaultOpen(
        tool({ tool: "search_kb", query: "docker", status: "running" }),
      ),
    ).toBe(false);
    expect(
      toolBlockDefaultOpen(
        tool({
          tool: "generate_image",
          query: "一只猫",
          attachments: ["媒体/生成/2026/cat.png"],
        }),
      ),
    ).toBe(false);
    expect(
      toolBlockDefaultOpen(
        tool({
          tool: "write_kb_file",
          attachments: ["媒体/生成/2026/logo.svg"],
        }),
      ),
    ).toBe(false);
    expect(
      toolBlockDefaultOpen(
        tool({
          tool: "sandbox_run",
          status: "running",
          query: "ls",
        }),
      ),
    ).toBe(false);
  });

  it("keeps unanswered asks open so the user can choose", () => {
    expect(
      toolBlockDefaultOpen(
        tool({
          tool: "ask_user",
          question_id: "q1",
          question: "继续吗？",
          options: [{ id: "a", label: "好" }],
        }),
      ),
    ).toBe(true);
    expect(
      toolBlockDefaultOpen(
        tool({
          tool: "ask_user",
          question_id: "q1",
          question: "继续吗？",
          options: [{ id: "a", label: "好" }],
          choice_resolved: "好",
        }),
      ),
    ).toBe(false);
  });
});
