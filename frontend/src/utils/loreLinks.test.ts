import { describe, expect, it } from "vitest";
import { parseLoreHref } from "./loreLinks";

const CID = "6d51bce5465f";

describe("parseLoreHref", () => {
  it("parses dm / rooms / channels conversation URIs", () => {
    expect(parseLoreHref(`lore://conversations/dm/default/${CID}/`)).toEqual({
      kind: "conversation",
      conversationId: CID,
    });
    expect(parseLoreHref(`lore://conversations/dm/default/${CID}`)).toEqual({
      kind: "conversation",
      conversationId: CID,
    });
    expect(
      parseLoreHref(`lore://conversations/dm/default/${CID}/msg-9`),
    ).toEqual({
      kind: "conversation",
      conversationId: CID,
      messageId: "msg-9",
    });
    expect(parseLoreHref(`lore://conversations/rooms/${CID}/`)).toEqual({
      kind: "conversation",
      conversationId: CID,
    });
    expect(
      parseLoreHref(`lore://conversations/rooms/${CID}/m1`),
    ).toEqual({
      kind: "conversation",
      conversationId: CID,
      messageId: "m1",
    });
    expect(
      parseLoreHref(`lore://conversations/channels/inst-1/${CID}/`),
    ).toEqual({
      kind: "conversation",
      conversationId: CID,
    });
    expect(
      parseLoreHref(`lore://conversations/channels/inst-1/${CID}/m2`),
    ).toEqual({
      kind: "conversation",
      conversationId: CID,
      messageId: "m2",
    });
  });

  it("parses kb file and directory with decoded path segments", () => {
    expect(parseLoreHref("lore://kb/notes/a.md")).toEqual({
      kind: "kb",
      path: "notes/a.md",
      isDir: false,
    });
    expect(parseLoreHref("lore://kb/%E6%8A%80%E8%83%BD/")).toEqual({
      kind: "kb",
      path: "技能",
      isDir: true,
    });
  });

  it("returns memory namespace", () => {
    expect(parseLoreHref("lore://memory/owner/identity/x")).toEqual({
      kind: "memory",
    });
  });

  it("rejects unsafe or unknown lore URIs", () => {
    expect(parseLoreHref("lore://kb/../x")).toBeNull();
    expect(parseLoreHref("lore://conversations/dm/default//")).toBeNull();
    expect(parseLoreHref("lore://conversations/dm/default/nothex")).toBeNull();
    expect(parseLoreHref("lore://unknown/x")).toBeNull();
    expect(parseLoreHref("conversation://abc")).toBeNull();
  });
});
