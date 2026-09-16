import { describe, expect, it } from "vitest";
import {
  buildResumeAssistantPatch,
  isSameTurnResumeAssistant,
} from "./resumeAssistantShell";

describe("isSameTurnResumeAssistant", () => {
  it("treats an unlabeled assistant as this turn's shell", () => {
    expect(
      isSameTurnResumeAssistant({ role: "assistant", text: "" }, "default"),
    ).toBe(true);
  });

  it("does not treat another labeled role as this turn", () => {
    expect(
      isSameTurnResumeAssistant(
        { role: "assistant", text: "", speaker_id: "general" },
        "game",
      ),
    ).toBe(false);
  });
});

describe("buildResumeAssistantPatch", () => {
  it("reuses the last assistant bubble in a 1:1 chat", () => {
    const base = [
      { role: "user" as const, text: "hi" },
      { role: "assistant" as const, text: "ok", model_name: "glm" },
    ];
    const result = buildResumeAssistantPatch(base);
    expect(result.streamingIndex).toBe(1);
    expect(result.messages).toHaveLength(2);
    expect(result.messages[0]).toBe(base[0]);
    expect(result.messages[1]).toMatchObject({
      role: "assistant",
      model_name: "glm",
      text: "ok",
    });
    expect(result.messages[1]).toBe(base[1]);
  });

  it("does not reuse another role's assistant bubble", () => {
    const base = [
      {
        role: "assistant" as const,
        text: "交给你了",
        speaker_id: "general",
        speaker_kind: "role" as const,
      },
    ];
    const result = buildResumeAssistantPatch(base, "game");
    expect(result.messages).toHaveLength(2);
    expect(result.messages[1]?.speaker_id).toBe("game");
    expect(result.streamingIndex).toBe(1);
  });

  it("reuses an unlabeled assistant and stamps the known speaker on reconnect", () => {
    const base = [
      { role: "user" as const, text: "问" },
      {
        role: "assistant" as const,
        text: "",
        timeline: [
          { type: "think" as const, ts: "t0", content: "用户问的是数学问题" },
        ],
      },
    ];
    const result = buildResumeAssistantPatch(base, "default");
    expect(result.messages).toHaveLength(2);
    expect(result.streamingIndex).toBe(1);
    expect(result.messages[1]).toMatchObject({
      role: "assistant",
      speaker_id: "default",
      speaker_kind: "role",
    });
    expect(result.messages[1]?.timeline).toEqual(base[1]?.timeline);
  });

  it("drops ghost same-turn assistant bubbles left by a previous reconnect", () => {
    const base = [
      { role: "user" as const, text: "问" },
      {
        role: "assistant" as const,
        timeline: [
          { type: "think" as const, ts: "t0", content: "半截思考" },
        ],
      },
      {
        role: "assistant" as const,
        speaker_id: "default",
        speaker_kind: "role" as const,
        text: "检索中",
        timeline: [
          { type: "think" as const, ts: "t0", content: "半截思考" },
          {
            type: "tool" as const,
            id: "t1",
            tool: "web_search",
            label: "搜索网页",
            ts: "t1",
            status: "running" as const,
          },
        ],
      },
    ];
    const result = buildResumeAssistantPatch(base, "default");
    expect(result.messages).toHaveLength(2);
    expect(result.messages[0]?.role).toBe("user");
    expect(result.messages[1]?.speaker_id).toBe("default");
    expect(result.messages[1]?.timeline?.some((b) => b.type === "tool")).toBe(
      true,
    );
    expect(result.streamingIndex).toBe(1);
  });

  it("appends after a role inbound so the next speaker gets a new bubble", () => {
    const base = [
      {
        role: "user" as const,
        text: "@游戏开发助手 请澄清",
        speaker_kind: "role" as const,
        speaker_id: "general",
      },
    ];
    const result = buildResumeAssistantPatch(base, "game");
    expect(result.messages[1]?.role).toBe("assistant");
    expect(result.messages[1]?.speaker_id).toBe("game");
  });
});
