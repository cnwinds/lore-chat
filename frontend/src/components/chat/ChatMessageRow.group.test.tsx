import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ChatMessageRow } from "./ChatMessageRow";
import type { ChatMessage, RoleSummary } from "../../api";

afterEach(() => {
  cleanup();
});

const roles: RoleSummary[] = [
  {
    id: "game",
    name: "游戏开发助手",
    avatar: null,
    system_prompt: "",
    is_default: false,
    sort_order: 1,
    created_at: "",
    updated_at: "",
  },
];

const baseProps = {
  isLiveStreaming: false,
  liveElapsedMs: 0,
  previewPath: null,
  conversationId: "g1",
  onOpenSource: () => {},
  onQuestionResolved: () => {},
  layout: "group" as const,
  roles,
};

describe("ChatMessageRow group layout", () => {
  it("shows a role name and avatar, not a 来自 tag", () => {
    const message: ChatMessage = {
      id: "m1",
      role: "assistant",
      text: "登录页改好了",
      speaker_kind: "role",
      speaker_id: "game",
      speaker_name: "游戏开发助手",
      ts: "2026-01-01T00:00:00.000Z",
    };
    render(<ChatMessageRow message={message} {...baseProps} />);
    expect(screen.getByText("游戏开发助手")).toBeTruthy();
    expect(screen.getByText("登录页改好了")).toBeTruthy();
    expect(screen.queryByText(/来自/)).toBeNull();
    expect(document.querySelector(".chat-row-group-role")).toBeTruthy();
    const row = document.querySelector(".chat-row-group-role");
    const col = row?.querySelector(".chat-row-group-col");
    expect(row?.firstElementChild).toBe(col);
    expect(col?.querySelector(".chat-row-group-head .role-avatar")).toBeTruthy();
    expect(row?.querySelector(".chat-row-group-name")?.textContent).toBe(
      "游戏开发助手",
    );
  });

  it("keeps the owner on the right", () => {
    const message: ChatMessage = {
      id: "m2",
      role: "user",
      text: "@游戏开发助手 改登录页",
      speaker_kind: "user",
      speaker_name: "主人",
      ts: "2026-01-01T00:00:00.000Z",
    };
    render(<ChatMessageRow message={message} {...baseProps} />);
    expect(document.querySelector(".chat-row-group-owner")).toBeTruthy();
    expect(screen.queryByText("主人")).toBeNull();
  });

  it("centers a system notice instead of drawing it as the owner", () => {
    const message: ChatMessage = {
      id: "m3",
      role: "user",
      text: "「游戏开发助手」的任务已超过预期时间，尚未回执。请询问进度或改派。",
      speaker_kind: "system",
      speaker_name: "系统",
      ts: "2026-01-01T00:00:00.000Z",
    };
    render(<ChatMessageRow message={message} {...baseProps} />);
    expect(document.querySelector(".chat-row-group-system")).toBeTruthy();
    expect(document.querySelector(".chat-row-group-owner")).toBeNull();
    expect(document.querySelector(".chat-bubble-system")).toBeTruthy();
    expect(screen.getByText(/超过预期/)).toBeTruthy();
  });
});

describe("ChatMessageRow user meta", () => {
  it("places the copy button immediately before the timestamp", () => {
    const message: ChatMessage = {
      id: "m-copy",
      role: "user",
      text: "你好",
      ts: "2026-01-01T14:32:00.000Z",
    };
    render(
      <ChatMessageRow
        message={message}
        isLiveStreaming={false}
        liveElapsedMs={0}
        previewPath={null}
        conversationId="c1"
        onOpenSource={() => {}}
        onQuestionResolved={() => {}}
      />,
    );
    const meta = document.querySelector(".chat-meta-user");
    const copy = meta?.querySelector(".chat-copy-btn");
    expect(copy).toBeTruthy();
    expect(copy?.nextElementSibling?.tagName).toBe("SPAN");
    expect(meta?.querySelector(".chat-meta-spacer")).toBeNull();
  });
});

describe("ChatMessageRow assistant meta", () => {
  it("lays out time with nested duration, then model, then copy", () => {
    const message: ChatMessage = {
      id: "a1",
      role: "assistant",
      text: "故事主线是第一地球。",
      ts: "2026-01-01T06:33:00.000Z",
      model_name: "glm-5.3-flash - max",
      total_duration_ms: 58200,
    };
    render(
      <ChatMessageRow
        message={message}
        isLiveStreaming={false}
        liveElapsedMs={0}
        previewPath={null}
        conversationId="c1"
        onOpenSource={() => {}}
        onQuestionResolved={() => {}}
      />,
    );
    const meta = document.querySelector(".chat-meta-assistant");
    const when = meta?.querySelector(".chat-meta-when");
    const cluster = meta?.querySelector(".chat-meta-model-wrap");
    const model = cluster?.querySelector(".chat-meta-model");
    const copy = meta?.querySelector(".chat-copy-btn");
    expect(when?.textContent).toMatch(/（58\.2s）/);
    expect(model?.textContent).toBe("glm-5.3-flash - max");
    expect(copy).toBeTruthy();
    expect(when?.nextElementSibling).toBe(cluster);
    expect(cluster?.nextElementSibling).toBe(
      meta?.querySelector(".chat-meta-actions"),
    );
    expect(document.querySelector(".chat-meta-tokens")).toBeNull();
  });

  it("tucks input/output tokens after the model name on desktop", () => {
    render(
      <ChatMessageRow
        message={{
          id: "a2",
          role: "assistant",
          text: "故事主线是第一地球。",
          ts: "2026-01-01T06:33:00.000Z",
          model_name: "glm-5.3-flash - max",
          total_duration_ms: 58200,
          prompt_tokens: 12345,
          completion_tokens: 678,
        }}
        isLiveStreaming={false}
        liveElapsedMs={0}
        previewPath={null}
        conversationId="c1"
        onOpenSource={() => {}}
        onQuestionResolved={() => {}}
      />,
    );
    const cluster = document.querySelector(".chat-meta-model-wrap");
    const model = cluster?.querySelector(".chat-meta-model");
    const tokens = cluster?.querySelector(".chat-meta-tokens");
    expect(model?.textContent).toBe("glm-5.3-flash - max");
    expect(tokens?.textContent).toBe("(in:12345·out:678)");
    expect(model?.nextElementSibling).toBe(tokens);
  });
});
