import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChatMessage } from "../types/chat";
import {
  buildConversationOutline,
  CONVERSATION_OUTLINE_MIN_ITEMS,
  flattenVisibleTranscriptMessages,
  formatOutlineLabel,
  getConversationOutlineActiveIndex,
  scrollToUserQuestion,
} from "./conversationOutline";

function user(
  id: string,
  text?: string,
  extra?: Partial<ChatMessage>,
): ChatMessage {
  return { id, role: "user", text, ...extra };
}

describe("formatOutlineLabel", () => {
  it("collapses whitespace and truncates with ellipsis", () => {
    expect(formatOutlineLabel("  hello   world  ")).toBe("hello world");
    const long = "一".repeat(80);
    const label = formatOutlineLabel(long, 72);
    expect(label.endsWith("…")).toBe(true);
    expect(label.length).toBe(73);
  });

  it("returns empty for blank text", () => {
    expect(formatOutlineLabel("   \n\t  ")).toBe("");
  });
});

describe("buildConversationOutline", () => {
  it("keeps user turns with text or attachments, old to new", () => {
    const msgs: ChatMessage[] = [
      user("u1", "第一问"),
      { id: "a1", role: "assistant", text: "答" },
      user("u2", "", { attachments: ["a.png"] }),
      user("u3", "   "),
      { role: "user", text: "无 id" },
      user("u4", "第三问"),
    ];
    const items = buildConversationOutline(msgs);
    expect(items.map((i) => i.messageId)).toEqual(["u1", "u2", "u4"]);
    expect(items.map((i) => i.index)).toEqual([1, 2, 3]);
    expect(items[1].label).toBe("（附件）");
    expect(items.length).toBeGreaterThanOrEqual(CONVERSATION_OUTLINE_MIN_ITEMS);
  });

  it("skips onboarding kickoff and injected user bubbles", () => {
    const items = buildConversationOutline([
      user("kick", "（系统）这个角色刚创建。", {
        client_message_id: "onboarding-kickoff:r1",
      }),
      user("inj", "插入", {
        injected: true,
        client_message_id: "inject:1",
      }),
      user("u1", "真实提问"),
    ]);
    expect(items.map((i) => i.messageId)).toEqual(["u1"]);
  });

  it("includes doc_context-only user turns as attachment placeholder", () => {
    const items = buildConversationOutline([
      user("u1", "", {
        doc_context: [{ path: "notes/a.md", kind: "document" }],
      }),
    ]);
    expect(items).toEqual([
      {
        messageId: "u1",
        index: 1,
        label: "（附件）",
        fullText: "（附件）",
      },
    ]);
  });
});

describe("flattenVisibleTranscriptMessages", () => {
  it("concatenates historical segments then tip, old to new", () => {
    const flat = flattenVisibleTranscriptMessages(
      [
        { messages: [user("h1", "更早"), { id: "ha", role: "assistant", text: "答" }] },
        { messages: [user("h2", "中间")] },
      ],
      [user("t1", "刚才")],
    );
    expect(flat.map((m) => m.id)).toEqual(["h1", "ha", "h2", "t1"]);
  });

  it("dedupes by message id so jump windows do not double-count tip", () => {
    const overlap = user("same", "重叠");
    const flat = flattenVisibleTranscriptMessages(
      [{ messages: [user("h1", "更早"), overlap] }],
      [overlap, user("t2", "新问")],
    );
    expect(flat.map((m) => m.id)).toEqual(["h1", "same", "t2"]);
  });

  it("treats missing segments as tip-only", () => {
    const tip = [user("t1", "刚才")];
    expect(flattenVisibleTranscriptMessages(undefined, tip)).toEqual(tip);
  });
});

describe("getConversationOutlineActiveIndex", () => {
  it("picks the last question whose top is above the threshold", () => {
    const root = document.createElement("div");
    Object.defineProperty(root, "getBoundingClientRect", {
      value: () => ({ top: 100, bottom: 500, left: 0, right: 400, width: 400, height: 400 }),
    });

    const mk = (id: string, top: number) => {
      const el = document.createElement("div");
      el.dataset.messageId = id;
      Object.defineProperty(el, "getBoundingClientRect", {
        value: () => ({ top, bottom: top + 40, left: 0, right: 100, width: 100, height: 40 }),
      });
      root.appendChild(el);
    };
    mk("u1", 80);
    mk("u2", 140);
    mk("u3", 220);

    const items = [
      { messageId: "u1", index: 1, label: "a", fullText: "a" },
      { messageId: "u2", index: 2, label: "b", fullText: "b" },
      { messageId: "u3", index: 3, label: "c", fullText: "c" },
    ];
    // threshold = 100 + 48 = 148 → u1 (80) and u2 (140) qualify
    expect(getConversationOutlineActiveIndex(root, items, 48)).toBe(1);
  });
});

describe("scrollToUserQuestion", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("scrolls target to top with offset and flashes", () => {
    vi.useFakeTimers();
    const root = document.createElement("div");
    root.scrollTop = 200;
    Object.defineProperty(root, "getBoundingClientRect", {
      value: () => ({ top: 50, bottom: 450, left: 0, right: 400, width: 400, height: 400 }),
    });
    const scrollTo = vi.fn();
    root.scrollTo = scrollTo as unknown as typeof root.scrollTo;

    const el = document.createElement("div");
    el.dataset.messageId = "u2";
    Object.defineProperty(el, "getBoundingClientRect", {
      value: () => ({ top: 180, bottom: 220, left: 0, right: 100, width: 100, height: 40 }),
    });
    root.appendChild(el);

    expect(scrollToUserQuestion(root, "u2", 12)).toBe(true);
    // nextTop = 200 + (180 - 50) - 12 = 318
    expect(scrollTo).toHaveBeenCalledWith({ top: 318, behavior: "smooth" });
    expect(el.classList.contains("chat-message-jump-flash")).toBe(true);
    vi.advanceTimersByTime(3000);
    expect(el.classList.contains("chat-message-jump-flash")).toBe(false);
    vi.useRealTimers();
  });
});
