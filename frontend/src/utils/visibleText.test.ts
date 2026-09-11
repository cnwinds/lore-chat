import { describe, expect, it } from "vitest";
import { getMessageCopyText } from "./chatMessageFormat";
import { stripProtocolMarkup } from "./visibleText";
import type { ChatMessage } from "../api";

describe("stripProtocolMarkup", () => {
  it("strips a lone old_function_results tag", () => {
    expect(stripProtocolMarkup("<old_function_results>")).toBe("");
    expect(stripProtocolMarkup("<old_function_results>\n")).toBe("");
  });

  it("strips a complete protocol block and keeps the reply", () => {
    expect(
      stripProtocolMarkup(
        '<old_function_results>\n{"ok":true}\n</old_function_results>\n你好',
      ),
    ).toBe("你好");
  });

  it("strips the same class of tool/function wrappers", () => {
    for (const tag of [
      "function_results",
      "tool_call",
      "tool_result",
      "minimax:tool_call",
    ]) {
      expect(stripProtocolMarkup(`<${tag}>payload</${tag}>\n结论`)).toBe("结论");
    }
  });

  it("keeps ordinary markup", () => {
    const text = "用 <div> 包一层，再画 <svg> 图标。";
    expect(stripProtocolMarkup(text)).toBe(text);
  });

  it("preserves protocol tags inside fenced code", () => {
    expect(stripProtocolMarkup("```\n<tool_call>search</tool_call>\n```")).toContain(
      "<tool_call>search</tool_call>",
    );
  });
});

describe("getMessageCopyText", () => {
  it("does not copy leaked protocol markup", () => {
    const m: ChatMessage = {
      role: "assistant",
      timeline: [
        { type: "text", ts: "t", content: "<old_function_results>" },
        { type: "text", ts: "t", content: "你好" },
      ],
    };
    expect(getMessageCopyText(m)).toBe("你好");
  });
});
