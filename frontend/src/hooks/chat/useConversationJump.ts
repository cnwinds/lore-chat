export type JumpTarget = {
  conversationId: string;
  /** 省略则只切换会话，不滚动到具体消息 */
  messageId?: string;
  startChar?: number;
  endChar?: number;
  offsetVersion?: string;
};

export type SearchJumpPlan = "wait" | "scroll" | "reveal" | "settle";

/** 搜索定位：已在内存里就滚；否则拉附近窗口，绝不一路翻页。 */
export function planSearchJump(input: {
  pendingJump: JumpTarget | null;
  msgs: { id?: string }[];
  historicalSegments: { messages: { id?: string }[] }[];
  loading: boolean;
  revealAttempted: boolean;
}): SearchJumpPlan {
  const target = input.pendingJump;
  if (!target?.messageId) return "wait";
  if (input.loading) return "wait";
  const mid = target.messageId;
  const present =
    input.msgs.some((m) => m.id === mid) ||
    input.historicalSegments.some((s) =>
      s.messages.some((m) => m.id === mid),
    );
  if (present) return "scroll";
  if (input.revealAttempted) return "settle";
  return "reveal";
}

export type HighlightRangeDetail = {
  start: number;
  end: number;
  offsetVersion?: string;
};

export function scrollToMessageHighlight(
  messageId: string,
  range?: { start: number; end: number },
  offsetVersion?: string,
): boolean {
  const el = document.querySelector(`[data-message-id="${messageId}"]`);
  if (!el) return false;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("chat-message-jump-flash");
  window.setTimeout(() => el.classList.remove("chat-message-jump-flash"), 3000);
  if (range) {
    el.dispatchEvent(
      new CustomEvent<HighlightRangeDetail>("highlight-range", {
        detail: { ...range, offsetVersion },
        bubbles: true,
      }),
    );
  }
  return true;
}
