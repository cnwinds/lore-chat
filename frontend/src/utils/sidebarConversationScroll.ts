/** 与 `.conversation-item` 的 `scroll-margin-top` 对齐（避开分组 sticky 标题） */
const CONVERSATION_LIST_STICKY_PAD_PX = 28;

/**
 * 仅当对话项未完整落在 `.conversation-list` 可视区内时滚动，
 * 避免列表刷新时误触发滚动。
 */
export function scrollConversationItemIntoView(el: HTMLElement): void {
  const list = el.closest(".conversation-list");
  if (!(list instanceof HTMLElement)) {
    el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    return;
  }
  const listRect = list.getBoundingClientRect();
  const elRect = el.getBoundingClientRect();
  const fullyVisible =
    elRect.top >= listRect.top + CONVERSATION_LIST_STICKY_PAD_PX &&
    elRect.bottom <= listRect.bottom;
  if (!fullyVisible) {
    el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}
