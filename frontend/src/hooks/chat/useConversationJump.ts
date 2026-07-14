export type JumpTarget = {
  conversationId: string;
  messageId: string;
  startChar?: number;
  endChar?: number;
  offsetVersion?: string;
};

export function scrollToMessageHighlight(
  messageId: string,
  range?: { start: number; end: number },
): boolean {
  const el = document.querySelector(`[data-message-id="${messageId}"]`);
  if (!el) return false;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add("chat-message-jump-flash");
  window.setTimeout(() => el.classList.remove("chat-message-jump-flash"), 3000);
  if (range) {
    el.dispatchEvent(
      new CustomEvent("highlight-range", {
        detail: range,
        bubbles: true,
      }),
    );
  }
  return true;
}
