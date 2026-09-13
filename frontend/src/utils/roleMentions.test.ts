import { describe, expect, it } from "vitest";
import {
  filterMentionRoles,
  mentionQueryAtCaret,
  parseMentionTokens,
  resolveMentionRoleIds,
} from "./roleMentions";

const roles = [
  { id: "default", name: "通用助手大师" },
  { id: "game", name: "游戏开发助手" },
];

describe("roleMentions", () => {
  it("parses @tokens from text", () => {
    expect(parseMentionTokens("请 @游戏开发助手 看一下 @default")).toEqual([
      "游戏开发助手",
      "default",
    ]);
  });

  it("resolves names and ids to role ids", () => {
    expect(
      resolveMentionRoleIds("@游戏开发助手 改登录页", roles),
    ).toEqual(["game"]);
    expect(resolveMentionRoleIds("找 @default", roles)).toEqual(["default"]);
  });

  it("detects an in-progress @ query at the caret", () => {
    expect(mentionQueryAtCaret("你好 @游", 5)).toEqual({ start: 3, query: "游" });
    expect(mentionQueryAtCaret("你好 游戏", 5)).toBeNull();
  });

  it("filters mention candidates by name, id, and member roster", () => {
    expect(filterMentionRoles(roles, "")).toEqual(roles);
    expect(filterMentionRoles(roles, "游戏")).toEqual([roles[1]]);
    expect(filterMentionRoles(roles, "DEFAULT")).toEqual([roles[0]]);
    expect(filterMentionRoles(roles, "", ["game"])).toEqual([roles[1]]);
    expect(filterMentionRoles(roles, "通", ["game"])).toEqual([]);
  });
});
