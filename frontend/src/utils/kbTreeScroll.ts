/**
 * 仅当知识库树节点未完整落在 `.sidebar-tree-scroll` 可视区内时滚动，
 * 避免展开态变化时误触发滚动。
 */
export function scrollKbTreeNodeIntoView(el: HTMLElement): void {
  const scrollRoot = el.closest(".sidebar-tree-scroll");
  if (!(scrollRoot instanceof HTMLElement)) {
    el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    return;
  }
  const rootRect = scrollRoot.getBoundingClientRect();
  const elRect = el.getBoundingClientRect();
  const fullyVisible =
    elRect.top >= rootRect.top && elRect.bottom <= rootRect.bottom;
  if (!fullyVisible) {
    el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}
