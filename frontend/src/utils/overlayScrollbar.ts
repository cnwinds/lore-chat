/** Overlay 滚动条：原生条隐藏不占位；滚动后画出可拖滑块，点轨道按页跳。 */

export const OVERLAY_SCROLL_HIDE_MS = 1000;
export const OVERLAY_SCROLL_MIN_THUMB = 32;
export const OVERLAY_SCROLL_RAIL_PX = 11;
export const OVERLAY_SCROLL_INSET_PX = 2;

export type OverlayAxis = "y" | "x";

export type Box = {
  top: number;
  left: number;
  right: number;
  bottom: number;
};

export function overlayThumbLayout(
  scrollSize: number,
  clientSize: number,
  scrollPos: number,
  railSize: number,
  minThumb: number = OVERLAY_SCROLL_MIN_THUMB,
): { thumbSize: number; thumbOffset: number } | null {
  const overflow = scrollSize - clientSize;
  if (overflow <= 1 || railSize <= 8) return null;
  const thumbSize = Math.min(
    railSize,
    Math.max(minThumb, (clientSize / scrollSize) * railSize),
  );
  const maxOffset = Math.max(0, railSize - thumbSize);
  const ratio = maxOffset === 0 ? 0 : Math.min(1, Math.max(0, scrollPos / overflow));
  return { thumbSize, thumbOffset: ratio * maxOffset };
}

export function scrollPosFromThumbOffset(
  thumbOffset: number,
  thumbSize: number,
  railSize: number,
  scrollSize: number,
  clientSize: number,
): number {
  const overflow = Math.max(0, scrollSize - clientSize);
  const maxOffset = Math.max(0, railSize - thumbSize);
  if (maxOffset <= 0) return 0;
  const ratio = Math.min(1, Math.max(0, thumbOffset / maxOffset));
  return ratio * overflow;
}

/** 点在滑块外的轨道上时，按一页翻（略小于一屏，贴近原生滚动条）。 */
export function overlayPageJump(
  clickOffset: number,
  thumbOffset: number,
  thumbSize: number,
  clientSize: number,
  scrollPos: number,
  overflow: number,
): number {
  if (clickOffset >= thumbOffset && clickOffset <= thumbOffset + thumbSize) {
    return scrollPos;
  }
  const dir = clickOffset < thumbOffset ? -1 : 1;
  return Math.min(overflow, Math.max(0, scrollPos + dir * clientSize * 0.9));
}

export function intersectBoxes(a: Box, b: Box): Box | null {
  const top = Math.max(a.top, b.top);
  const left = Math.max(a.left, b.left);
  const right = Math.min(a.right, b.right);
  const bottom = Math.min(a.bottom, b.bottom);
  if (right - left < 8 || bottom - top < 8) return null;
  return { top, left, right, bottom };
}

export function resolveScrollTarget(target: EventTarget | null): HTMLElement | null {
  if (target === document) return document.documentElement;
  if (target instanceof HTMLElement) return target;
  if (target instanceof Node) return target.parentElement;
  return null;
}

function axisCanOverflow(style: CSSStyleDeclaration, axis: OverlayAxis): boolean {
  const value = axis === "y" ? style.overflowY : style.overflowX;
  return value === "auto" || value === "scroll" || value === "overlay";
}

function elementHasOverflow(el: HTMLElement, style: CSSStyleDeclaration): boolean {
  const y =
    (isDocumentScroller(el) || axisCanOverflow(style, "y")) &&
    el.scrollHeight > el.clientHeight + 1;
  const x =
    (isDocumentScroller(el) || axisCanOverflow(style, "x")) &&
    el.scrollWidth > el.clientWidth + 1;
  return y || x;
}

/** 从事件目标向上找到正在滚的 overflow 容器。 */
export function findScrollableAncestor(start: EventTarget | null): HTMLElement | null {
  let node: HTMLElement | null = resolveScrollTarget(start);
  while (node) {
    if (
      node.classList.contains("lore-scroll-rail") ||
      node.classList.contains("lore-scroll-thumb")
    ) {
      node = node.parentElement;
      continue;
    }
    const style = getComputedStyle(node);
    if (elementHasOverflow(node, style)) {
      return node === document.body ? document.documentElement : node;
    }
    if (node === document.documentElement) break;
    node = node.parentElement;
  }
  return null;
}

function isDocumentScroller(el: HTMLElement): boolean {
  return el === document.documentElement || el === document.body;
}

function boxFromRect(r: DOMRectReadOnly): Box {
  return { top: r.top, left: r.left, right: r.right, bottom: r.bottom };
}

function visibleScrollerBox(el: HTMLElement): Box | null {
  if (isDocumentScroller(el)) {
    return {
      top: 0,
      left: 0,
      right: window.innerWidth,
      bottom: window.innerHeight,
    };
  }
  let box: Box | null = boxFromRect(el.getBoundingClientRect());
  let node = el.parentElement;
  while (box && node) {
    const style = getComputedStyle(node);
    if (
      axisCanOverflow(style, "y") ||
      axisCanOverflow(style, "x") ||
      style.overflowY === "hidden" ||
      style.overflowY === "clip" ||
      style.overflowX === "hidden" ||
      style.overflowX === "clip"
    ) {
      box = intersectBoxes(box, boxFromRect(node.getBoundingClientRect()));
    }
    node = node.parentElement;
  }
  if (!box) return null;
  return intersectBoxes(box, {
    top: 0,
    left: 0,
    right: window.innerWidth,
    bottom: window.innerHeight,
  });
}

type Rail = {
  root: HTMLDivElement;
  thumb: HTMLDivElement;
  axis: OverlayAxis;
};

let started = false;
let hideTimer = 0;
let active: HTMLElement | null = null;
let dragging: OverlayAxis | null = null;
let hoverRail = false;
let dragOrigin = 0;
let dragScrollOrigin = 0;
let dragThumbOrigin = 0;
let rails: { y: Rail; x: Rail } | null = null;

function makeRail(axis: OverlayAxis): Rail {
  const root = document.createElement("div");
  root.className = `lore-scroll-rail lore-scroll-rail--${axis}`;
  root.setAttribute("aria-hidden", "true");
  const thumb = document.createElement("div");
  thumb.className = "lore-scroll-thumb";
  root.appendChild(thumb);
  document.body.appendChild(root);
  return { root, thumb, axis };
}

function clearHideTimer() {
  if (hideTimer) {
    window.clearTimeout(hideTimer);
    hideTimer = 0;
  }
}

function hideRails() {
  if (!rails || dragging || hoverRail) return;
  rails.y.root.classList.remove("is-visible");
  rails.x.root.classList.remove("is-visible");
  active = null;
}

function scheduleHide() {
  clearHideTimer();
  hideTimer = window.setTimeout(hideRails, OVERLAY_SCROLL_HIDE_MS);
}

function metrics(el: HTMLElement, axis: OverlayAxis) {
  if (axis === "y") {
    return {
      scrollSize: el.scrollHeight,
      clientSize: el.clientHeight,
      scrollPos: el.scrollTop,
    };
  }
  return {
    scrollSize: el.scrollWidth,
    clientSize: el.clientWidth,
    scrollPos: el.scrollLeft,
  };
}

function paintRail(el: HTMLElement, rail: Rail, box: Box): boolean {
  const inset = OVERLAY_SCROLL_INSET_PX;
  const thick = OVERLAY_SCROLL_RAIL_PX;
  const m = metrics(el, rail.axis);
  const railSize =
    rail.axis === "y" ? box.bottom - box.top - inset * 2 : box.right - box.left - inset * 2;
  const layout = overlayThumbLayout(
    m.scrollSize,
    m.clientSize,
    m.scrollPos,
    railSize,
  );
  if (!layout) {
    rail.root.classList.remove("is-visible");
    return false;
  }
  if (rail.axis === "y") {
    rail.root.style.top = `${box.top + inset}px`;
    rail.root.style.left = `${box.right - thick}px`;
    rail.root.style.height = `${Math.max(0, box.bottom - box.top - inset * 2)}px`;
    rail.root.style.width = `${thick}px`;
    rail.thumb.style.top = `${layout.thumbOffset}px`;
    rail.thumb.style.height = `${layout.thumbSize}px`;
    rail.thumb.style.left = "";
    rail.thumb.style.width = "";
  } else {
    rail.root.style.left = `${box.left + inset}px`;
    rail.root.style.top = `${box.bottom - thick}px`;
    rail.root.style.width = `${Math.max(0, box.right - box.left - inset * 2)}px`;
    rail.root.style.height = `${thick}px`;
    rail.thumb.style.left = `${layout.thumbOffset}px`;
    rail.thumb.style.width = `${layout.thumbSize}px`;
    rail.thumb.style.top = "";
    rail.thumb.style.height = "";
  }
  rail.root.classList.add("is-visible");
  return true;
}

function paint(el: HTMLElement) {
  if (!rails) return;
  const box = visibleScrollerBox(el);
  if (!box) {
    hideRails();
    return;
  }
  const y = paintRail(el, rails.y, box);
  const x = paintRail(el, rails.x, box);
  if (!y && !x && !dragging) {
    hideRails();
    return;
  }
  active = el;
  if (!dragging && !hoverRail) scheduleHide();
}

function revealFromEvent(event: Event) {
  const el = findScrollableAncestor(event.target);
  if (!el || !rails) return;
  requestAnimationFrame(() => paint(el));
}

function onScroll(event: Event) {
  const el = findScrollableAncestor(event.target) ?? resolveScrollTarget(event.target);
  if (!el || !rails) return;
  if (el.classList.contains("lore-scroll-rail") || el.classList.contains("lore-scroll-thumb")) {
    return;
  }
  paint(el);
}

function railOf(target: EventTarget | null): Rail | null {
  if (!rails || !(target instanceof Element)) return null;
  if (rails.y.root === target || rails.y.thumb === target) return rails.y;
  if (rails.x.root === target || rails.x.thumb === target) return rails.x;
  return null;
}

function onPointerDown(event: PointerEvent) {
  if (!active || !rails) return;
  const rail = railOf(event.target);
  if (!rail) return;
  event.preventDefault();
  event.stopPropagation();
  const m = metrics(active, rail.axis);
  const railRect = rail.root.getBoundingClientRect();
  const railSize = rail.axis === "y" ? railRect.height : railRect.width;
  const layout = overlayThumbLayout(m.scrollSize, m.clientSize, m.scrollPos, railSize);
  if (!layout) return;
  const clickOffset =
    rail.axis === "y" ? event.clientY - railRect.top : event.clientX - railRect.left;
  const onThumb = event.target === rail.thumb;
  if (!onThumb) {
    const next = overlayPageJump(
      clickOffset,
      layout.thumbOffset,
      layout.thumbSize,
      m.clientSize,
      m.scrollPos,
      m.scrollSize - m.clientSize,
    );
    if (rail.axis === "y") active.scrollTop = next;
    else active.scrollLeft = next;
    paint(active);
    return;
  }
  dragging = rail.axis;
  rail.root.classList.add("is-dragging");
  dragOrigin = rail.axis === "y" ? event.clientY : event.clientX;
  dragScrollOrigin = m.scrollPos;
  dragThumbOrigin = layout.thumbOffset;
  rail.thumb.setPointerCapture(event.pointerId);
  clearHideTimer();
}

function onPointerMove(event: PointerEvent) {
  if (!dragging || !active || !rails) return;
  const rail = dragging === "y" ? rails.y : rails.x;
  const m = metrics(active, dragging);
  const railRect = rail.root.getBoundingClientRect();
  const railSize = dragging === "y" ? railRect.height : railRect.width;
  const layout = overlayThumbLayout(
    m.scrollSize,
    m.clientSize,
    dragScrollOrigin,
    railSize,
  );
  if (!layout) return;
  const delta =
    (dragging === "y" ? event.clientY : event.clientX) - dragOrigin;
  const next = scrollPosFromThumbOffset(
    dragThumbOrigin + delta,
    layout.thumbSize,
    railSize,
    m.scrollSize,
    m.clientSize,
  );
  if (dragging === "y") active.scrollTop = next;
  else active.scrollLeft = next;
  paint(active);
}

function onPointerUp(event: PointerEvent) {
  if (!dragging || !rails) return;
  const rail = dragging === "y" ? rails.y : rails.x;
  dragging = null;
  rail.root.classList.remove("is-dragging");
  if (rail.thumb.hasPointerCapture(event.pointerId)) {
    rail.thumb.releasePointerCapture(event.pointerId);
  }
  scheduleHide();
}

function onRailEnter() {
  hoverRail = true;
  clearHideTimer();
}

function onRailLeave() {
  hoverRail = false;
  if (!dragging) scheduleHide();
}

function onResize() {
  if (active) paint(active);
}

function mount() {
  rails = { y: makeRail("y"), x: makeRail("x") };
  document.addEventListener("scroll", onScroll, true);
  document.addEventListener("wheel", revealFromEvent, { capture: true, passive: true });
  document.addEventListener("touchmove", revealFromEvent, { capture: true, passive: true });
  window.addEventListener("resize", onResize);
  for (const rail of [rails.y, rails.x]) {
    rail.root.addEventListener("pointerdown", onPointerDown);
    rail.root.addEventListener("pointerenter", onRailEnter);
    rail.root.addEventListener("pointerleave", onRailLeave);
  }
  document.addEventListener("pointermove", onPointerMove);
  document.addEventListener("pointerup", onPointerUp);
  document.addEventListener("pointercancel", onPointerUp);
}

function unmount() {
  clearHideTimer();
  document.removeEventListener("scroll", onScroll, true);
  document.removeEventListener("wheel", revealFromEvent, true);
  document.removeEventListener("touchmove", revealFromEvent, true);
  window.removeEventListener("resize", onResize);
  document.removeEventListener("pointermove", onPointerMove);
  document.removeEventListener("pointerup", onPointerUp);
  document.removeEventListener("pointercancel", onPointerUp);
  if (rails) {
    rails.y.root.remove();
    rails.x.root.remove();
  }
  rails = null;
  active = null;
  dragging = null;
  hoverRail = false;
}

export function initOverlayScrollbar(): void {
  if (started || typeof document === "undefined") return;
  started = true;
  if (document.body) mount();
  else document.addEventListener("DOMContentLoaded", mount, { once: true });
}

/** 仅测试用：卸掉宿主，避免用例互相污染。 */
export function resetOverlayScrollbarForTests(): void {
  unmount();
  started = false;
}
