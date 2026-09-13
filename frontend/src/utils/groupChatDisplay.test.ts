import { describe, expect, it } from "vitest";
import {
  isOwnerSpeaker,
  membersFromRoleIds,
  mentionCandidatesForRoom,
  resolveGroupSpeaker,
} from "./groupChatDisplay";

describe("groupChatDisplay", () => {
  it("treats unmarked user messages as the owner", () => {
    expect(isOwnerSpeaker({ role: "user", text: "hi" })).toBe(true);
    expect(
      isOwnerSpeaker({ role: "user", text: "hi", speaker_kind: "role" }),
    ).toBe(false);
  });

  it("resolves a role speaker from the roster", () => {
    const speaker = resolveGroupSpeaker(
      {
        role: "assistant",
        text: "好",
        speaker_kind: "role",
        speaker_id: "game",
      },
      [{ id: "game", name: "游戏开发助手", avatar: null } as never],
    );
    expect(speaker).toMatchObject({
      kind: "role",
      name: "游戏开发助手",
      id: "game",
    });
  });

  it("maps role ids to members when the card has no briefs", () => {
    expect(
      membersFromRoleIds(["a", "b"], [
        { id: "a", name: "通用助手大师", avatar: null } as never,
        { id: "b", name: "游戏开发助手", avatar: null } as never,
      ]),
    ).toEqual([
      { id: "a", name: "通用助手大师", avatar: null },
      { id: "b", name: "游戏开发助手", avatar: null },
    ]);
  });

  it("lists group members for @, not the whole role roster", () => {
    const roles = [
      { id: "a", name: "通用助手大师", avatar: "a.png" } as never,
      { id: "b", name: "游戏开发助手", avatar: null } as never,
      { id: "c", name: "闲人", avatar: null } as never,
    ];
    expect(
      mentionCandidatesForRoom({
        roomMode: "group",
        roles,
        participants: [{ id: "b", name: "游戏开发助手", avatar: null }],
      }),
    ).toEqual([{ id: "b", name: "游戏开发助手", avatar: null }]);
    expect(
      mentionCandidatesForRoom({
        roomMode: "role",
        roles,
        participants: [],
      }).map((r) => r.id),
    ).toEqual(["a", "b", "c"]);
  });
});
