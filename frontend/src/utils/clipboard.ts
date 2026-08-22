import { isImageFile } from "./kbImageUrls";

/** 粘贴事件里可读的剪贴板片段（便于单测 mock，无需完整 DataTransfer）。 */
export type ClipboardPasteSource = {
  items?: ArrayLike<{
    kind: string;
    type: string;
    getAsFile: () => File | null;
  }>;
  files?: ArrayLike<File>;
};

/**
 * 从剪贴板提取全部文件项（资源管理器复制文件 / 截图等）。
 * 优先 items 中 kind=file；否则回退 files 列表。
 */
export function extractClipboardFiles(
  data: ClipboardPasteSource | null | undefined,
): File[] {
  if (!data) return [];
  const out: File[] = [];
  const items = data.items;
  if (items && items.length > 0) {
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (!item || item.kind !== "file") continue;
      const file = item.getAsFile();
      if (file) out.push(file);
    }
    if (out.length) return out;
  }
  const files = data.files;
  if (files && files.length > 0) {
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      if (file) out.push(file);
    }
  }
  return out;
}

/**
 * 从剪贴板提取图片文件（截图 / 复制图片）。
 */
export function extractClipboardImageFiles(
  data: ClipboardPasteSource | null | undefined,
): File[] {
  return extractClipboardFiles(data).filter((f) => isImageFile(f));
}

/** 复制到剪贴板：优先 Clipboard API，HTTP 非安全上下文回退 execCommand。 */
export async function copyTextToClipboard(text: string): Promise<boolean> {
  const value = text ?? "";
  if (
    typeof navigator !== "undefined" &&
    navigator.clipboard &&
    typeof navigator.clipboard.writeText === "function" &&
    typeof window !== "undefined" &&
    window.isSecureContext
  ) {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      /* fall through */
    }
  }
  return copyViaExecCommand(value);
}

function copyViaExecCommand(text: string): boolean {
  if (typeof document === "undefined") return false;
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  ta.style.top = "0";
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  ta.setSelectionRange(0, ta.value.length);
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  document.body.removeChild(ta);
  return ok;
}
