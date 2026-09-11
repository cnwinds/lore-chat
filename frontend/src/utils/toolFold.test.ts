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
  it("collapses finished sandbox and staging tools when the turn is not live", () => {
    expect(
      toolBlockDefaultOpen(
        tool({
          tool: "sandbox_run",
          query: "python --version",
          progress_log: ["Python 3.12.0"],
        }),
        { isLive: false },
      ),
    ).toBe(false);
    expect(
      toolBlockDefaultOpen(
        tool({
          tool: "stage_to_sandbox",
          summary: "投放 1 个文件",
          progress_log: ["Traceback (most recent call last):"],
        }),
        { isLive: false },
      ),
    ).toBe(false);
  });

  it("keeps generated image and svg attachments open after the turn ends", () => {
    expect(
      toolBlockDefaultOpen(
        tool({
          tool: "generate_image",
          query: "一只猫",
          attachments: ["媒体/生成/2026/cat.png"],
        }),
        { isLive: false },
      ),
    ).toBe(true);
    expect(
      toolBlockDefaultOpen(
        tool({
          tool: "write_kb_file",
          attachments: ["媒体/生成/2026/logo.svg"],
        }),
        { isLive: false },
      ),
    ).toBe(true);
    expect(
      toolBlockDefaultOpen(
        tool({
          tool: "publish_from_sandbox",
          attachments: ["媒体/生成/2026/icon.png"],
        }),
        { isLive: false },
      ),
    ).toBe(true);
  });

  it("does not treat a mention of an image path in summary as a reason to expand", () => {
    expect(
      toolBlockDefaultOpen(
        tool({
          tool: "read_doc",
          summary: "读了 媒体/生成/2026/logo.svg",
        }),
        { isLive: false },
      ),
    ).toBe(false);
  });

  it("keeps unanswered asks open after the turn ends", () => {
    expect(
      toolBlockDefaultOpen(
        tool({
          tool: "ask_user",
          question_id: "q1",
          question: "继续吗？",
          options: [{ id: "a", label: "好" }],
        }),
        { isLive: false },
      ),
    ).toBe(true);
  });

  it("expands non-search tools while streaming, but still folds search", () => {
    expect(
      toolBlockDefaultOpen(
        tool({
          tool: "sandbox_run",
          status: "running",
          query: "ls",
        }),
        { isLive: true },
      ),
    ).toBe(true);
    expect(
      toolBlockDefaultOpen(
        tool({ tool: "search_kb", query: "docker", status: "running" }),
        { isLive: true },
      ),
    ).toBe(false);
  });
});
