import { describe, expect, it } from "vitest";
import { buildResumeAssistantPatch } from "./resumeAssistantShell";

describe("buildResumeAssistantPatch", () => {
  it("reuses the last assistant bubble in a 1:1 chat", () => {
    const base = [
      { role: "user" as const, text: "hi" },
      { role: "assistant" as const, text: "ok" },
    ];
    const result = buildResumeAssistantPatch(base);
    expect(result.messages).toBe(base);
    expect(result.streamingIndex).toBe(1);
  });

  it("does not reuse another role's assistant bubble", () => {
    const base = [
      {
        role: "assistant" as const,
        text: "交给你了",
        speaker_id: "general",
        speaker_kind: "role",
      },
    ];
    const result = buildResumeAssistantPatch(base, "game");
    expect(result.messages).toHaveLength(2);
    expect(result.messages[1]?.speaker_id).toBe("game");
    expect(result.streamingIndex).toBe(1);
  });

  it("does not reuse an unlabeled assistant when the next speaker is known", () => {
    const base = [{ role: "assistant" as const, text: "" }];
    const result = buildResumeAssistantPatch(base, "game");
    expect(result.messages).toHaveLength(2);
    expect(result.messages[1]?.speaker_id).toBe("game");
  });

  it("appends after a role inbound so the next speaker gets a new bubble", () => {
    const base = [
      {
        role: "user" as const,
        text: "@游戏开发助手 请澄清",
        speaker_kind: "role",
        speaker_id: "general",
      },
    ];
    const result = buildResumeAssistantPatch(base, "game");
    expect(result.messages[1]?.role).toBe("assistant");
    expect(result.messages[1]?.speaker_id).toBe("game");
  });
});
