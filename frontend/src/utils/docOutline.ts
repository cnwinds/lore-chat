export type OutlineItem = {
  id: string;
  level: number;
  text: string;
  line: number;
  index: number;
};

const PREVIEW_HEADING_SELECTOR =
  ".doc-live-preview .ProseMirror h1, .doc-live-preview .ProseMirror h2, .doc-live-preview .ProseMirror h3, .doc-live-preview .ProseMirror h4, .doc-live-preview .ProseMirror h5, .doc-live-preview .ProseMirror h6";

/** 从 Markdown 源码解析 ATX 标题（# …） */
export function parseDocOutline(body: string): OutlineItem[] {
  const items: OutlineItem[] = [];
  const lines = body.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^(#{1,6})\s+(.+)$/);
    if (!m) continue;
    const text = stripMarkdownInline(m[2].trim());
    if (!text) continue;
    items.push({
      id: `line-${i}`,
      level: m[1].length,
      text,
      line: i,
      index: items.length,
    });
  }
  return items;
}

function stripMarkdownInline(raw: string): string {
  return raw
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/_([^_]+)_/g, "$1")
    .replace(/\s+#+\s*$/, "")
    .trim();
}

/** Preview 模式：根据滚动位置返回当前应高亮的目录项 index */
export function getPreviewOutlineActiveIndex(
  scrollRoot: HTMLElement | null,
  offsetPx = 72,
): number {
  if (!scrollRoot) return -1;
  const headings = scrollRoot.querySelectorAll<HTMLElement>(PREVIEW_HEADING_SELECTOR);
  if (headings.length === 0) return -1;

  const threshold = scrollRoot.getBoundingClientRect().top + offsetPx;
  let active = -1;
  for (let i = 0; i < headings.length; i++) {
    if (headings[i].getBoundingClientRect().top <= threshold + 2) {
      active = i;
    } else {
      break;
    }
  }
  if (active === -1 && scrollRoot.scrollTop < 48) return 0;
  return active;
}

function getSourceLineAtScroll(textarea: HTMLTextAreaElement): number {
  const style = getComputedStyle(textarea);
  const lineHeight =
    parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.65 || 20;
  const paddingTop = parseFloat(style.paddingTop) || 0;
  const visibleTop = textarea.scrollTop + paddingTop + lineHeight * 0.5;
  return Math.max(0, Math.floor(visibleTop / lineHeight));
}

/** Markdown 源码模式：根据 textarea 滚动行号返回目录项 index */
export function getSourceOutlineActiveIndex(
  textarea: HTMLTextAreaElement | null,
  items: OutlineItem[],
): number {
  if (!textarea || items.length === 0) return -1;
  const line = getSourceLineAtScroll(textarea);
  let active = -1;
  for (let i = 0; i < items.length; i++) {
    if (items[i].line <= line) active = i;
    else break;
  }
  return active;
}

export function jumpToOutlineInPreview(
  scrollRoot: HTMLElement | null,
  item: OutlineItem,
): void {
  if (!scrollRoot) return;
  const headings = scrollRoot.querySelectorAll<HTMLElement>(PREVIEW_HEADING_SELECTOR);
  const target = headings[item.index];
  if (!target) return;
  target.scrollIntoView({ behavior: "smooth", block: "start" });
  target.classList.remove("doc-outline-flash");
  void target.offsetWidth;
  target.classList.add("doc-outline-flash");
}

export function jumpToOutlineInSource(
  textarea: HTMLTextAreaElement | null,
  line: number,
): void {
  if (!textarea) return;
  const lines = textarea.value.split("\n");
  let start = 0;
  for (let i = 0; i < line; i++) {
    start += lines[i].length + 1;
  }
  textarea.focus();
  textarea.setSelectionRange(start, start);
  const style = getComputedStyle(textarea);
  const lineHeight =
    parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.65 || 20;
  const paddingTop = parseFloat(style.paddingTop) || 0;
  textarea.scrollTop = Math.max(
    0,
    line * lineHeight + paddingTop - textarea.clientHeight / 3,
  );
}
