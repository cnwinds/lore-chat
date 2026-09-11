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

  it("keeps generated svg attachments expanded after the turn ends", () => {
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
      "true",
    );
    expect(document.querySelector(".timeline-tool-attachments")).not.toBeNull();
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
});
