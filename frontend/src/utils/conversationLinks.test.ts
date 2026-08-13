import { describe, expect, it } from "vitest";
import {
  buildConversationHref,
  linkifyConversationCitations,
  parseConversationHref,
} from "./conversationLinks";

describe("conversationLinks", () => {
  it("parses conversation:// cid and optional message", () => {
    expect(parseConversationHref("conversation://6d51bce5465f")).toEqual({
      conversationId: "6d51bce5465f",
    });
    expect(
      parseConversationHref("conversation://6d51bce5465f/msg-1"),
    ).toEqual({
      conversationId: "6d51bce5465f",
      messageId: "msg-1",
    });
    expect(parseConversationHref("https://example.com")).toBeNull();
  });

  it("linkifies 会话：cid 标题：… blocks", () => {
    const src =
      "📌 会话：6d51bce5465f 标题： https://www.qbitai.com/2026/08/468766.ht… 时间： 2026-08-10 11:21 ～ 08-11（跨两天）";
    const out = linkifyConversationCitations(src);
    expect(out).toContain("[https://www.qbitai.com/2026/08/468766.ht…](");
    expect(out).toContain("conversation://6d51bce5465f)");
    expect(out).toContain("时间： 2026-08-10");
    expect(out).not.toMatch(/会话：6d51bce5465f/);
  });

  it("linkifies backtick-wrapped session ids", () => {
    const src = "**📌 会话：`6d51bce5465f`**\n**标题：** x";
    const out = linkifyConversationCitations(src);
    expect(out).toContain("conversation://6d51bce5465f");
    expect(out).not.toContain("`6d51bce5465f`");
  });

  it("buildConversationHref", () => {
    expect(buildConversationHref("ABC")).toBe("conversation://abc");
    expect(buildConversationHref("abc", "m1")).toBe("conversation://abc/m1");
  });
});
