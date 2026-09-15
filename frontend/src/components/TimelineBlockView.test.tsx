import { cleanup, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { TimelineBlock } from "../types/chat";
import { TimelineBlockView } from "./TimelineBlockView";

const emptyCumulative = {
  toolCumulative: new Map<string, number>(),
  parallelCumulative: new Map<string, number>(),
};

function renderBlock(block: TimelineBlock, isLive = false) {
  cleanup();
  return render(
    <TimelineBlockView
      block={block}
      cumulative={emptyCumulative}
      isLive={isLive}
      onOpenSource={() => {}}
    />,
  );
}

describe("TimelineBlockView default fold", () => {
  it("collapses finished sandbox tools in a completed turn", () => {
    renderBlock({
      type: "tool",
      id: "sb1",
      tool: "sandbox_run",
      label: "在沙箱执行命令",
      ts: "t",
      status: "done",
      query: "python --version",
      progress_log: ["Python 3.12.0"],
      summary: "exit=0",
    });
    expect(screen.getByRole("button", { name: /在沙箱执行命令/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(document.querySelector(".timeline-tool-body")).toBeNull();
  });

  it("collapses generated svg attachments until the user expands them", () => {
    renderBlock({
      type: "tool",
      id: "svg1",
      tool: "write_kb_file",
      label: "写入知识库矢量图",
      ts: "t",
      status: "done",
      attachments: ["媒体/生成/2026/logo.svg"],
      summary: "已写入 logo.svg",
    });
    expect(screen.getByRole("button", { name: /写入知识库矢量图/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(document.querySelector(".timeline-tool-attachments")).toBeNull();
  });

  it("renders send_message as a collaboration card", () => {
    renderBlock({
      type: "tool",
      id: "sm1",
      tool: "send_message",
      label: "发给其他角色",
      ts: "t",
      status: "done",
      summary: "已发送。协作房间 conversation://aaaaaaaaaaaa",
      room_id: "aaaaaaaaaaaa",
      target_role_name: "游戏开发助手",
      wake_status: "queued",
    });
    expect(document.querySelector(".timeline-collab-card")).not.toBeNull();
    expect(screen.getByText(/协作 · 游戏开发助手/)).toBeTruthy();
    expect(screen.getByText("排队中")).toBeTruthy();
  });

  it("collapses think blocks even while the turn is live", () => {
    renderBlock(
      {
        type: "think",
        ts: "t",
        content: "先看链接再总结",
      },
      true,
    );
    expect(screen.getByRole("button", { name: /思考过程/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("collapses think blocks when the turn is no longer live", () => {
    renderBlock({
      type: "think",
      ts: "t",
      content: "先看链接再总结",
    });
    expect(screen.getByRole("button", { name: /思考过程/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("shows duration on a collapsed think header", () => {
    renderBlock({
      type: "think",
      ts: "t",
      content: "先看链接再总结",
      duration_ms: 1500,
    });
    expect(screen.getByText("1.5s")).toBeTruthy();
  });

  it("shows a live stopwatch while thinking", () => {
    cleanup();
    render(
      <TimelineBlockView
        block={{
          type: "think",
          ts: "t",
          content: "hmm",
          started_at_ms: 1000,
        }}
        cumulative={emptyCumulative}
        isLive
        nowMs={2500}
        onOpenSource={() => {}}
      />,
    );
    expect(screen.getByText("1.5s")).toBeTruthy();
  });

  it("keeps unanswered asks expanded so choices stay visible", () => {
    renderBlock({
      type: "tool",
      id: "q1",
      tool: "ask_user",
      label: "征询",
      ts: "t",
      status: "done",
      question_id: "q1",
      question: "继续吗？",
      options: [{ id: "a", label: "好" }],
    });
    expect(screen.getByRole("button", { name: /征询/ })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });
});
