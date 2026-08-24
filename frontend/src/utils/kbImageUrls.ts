import { downloadUrl } from "../api";

const IMAGE_EXT = /\.(png|jpe?g|gif|webp|bmp|svg|tif|tiff|ico)$/i;

/** 是否像知识库内相对路径（非 http(s)/data/绝对 URL）。 */
export function isKbRelativeImagePath(src: string): boolean {
  const s = src.trim();
  if (!s) return false;
  if (/^(https?:|data:|blob:|\/\/)/i.test(s)) return false;
  if (s.startsWith("/api/")) return false;
  return true;
}

export function isLikelyImagePath(path: string): boolean {
  return IMAGE_EXT.test(path.split("?")[0] || path);
}

/** 绝对 URL / 已是 API 能力链时原样返回，否则走需登录的 download。 */
export function mediaDisplayUrl(path: string): string {
  const s = path.trim();
  if (!s) return s;
  if (/^(https?:|data:|blob:)/i.test(s) || s.startsWith("/api/")) return s;
  return downloadUrl(s);
}

export function isMediaGrantUrl(path: string): boolean {
  return path.includes("/api/media/grant/");
}

/** 聊天/分享里可作图片预览的引用（相对路径或 media grant）。 */
export function isDisplayableImageRef(path: string): boolean {
  const s = path.trim();
  if (!s) return false;
  if (/^https?:\/\//i.test(s)) return isMediaGrantUrl(s) || isLikelyImagePath(s);
  return isLikelyImagePath(s);
}

/** File / 剪贴板图：优先 MIME，否则文件名后缀（与 isLikelyImagePath 同源）。 */
export function isImageFile(file: File, name?: string): boolean {
  if (file.type.startsWith("image/")) return true;
  return isLikelyImagePath(name ?? file.name);
}

export function imageExtFromFile(file: File, name?: string): string {
  const n = name ?? file.name;
  const m = n.match(IMAGE_EXT);
  if (m) return m[0].toLowerCase();
  const mime = file.type.toLowerCase();
  if (mime === "image/jpeg") return ".jpg";
  if (mime === "image/png") return ".png";
  if (mime === "image/webp") return ".webp";
  if (mime === "image/gif") return ".gif";
  if (mime === "image/bmp") return ".bmp";
  if (mime === "image/svg+xml") return ".svg";
  return ".bin";
}

/** 渲染用：相对路径 → /api/download?path=... */
export function kbImageSrcForDisplay(src: string): string {
  const s = src.trim();
  if (!isKbRelativeImagePath(s)) return s;
  return downloadUrl(s);
}

/**
 * 把 md 里的相对图片路径改成可加载的 download URL（仅展示）。
 * 不改 http(s)/data/已是 /api/download 的链接。
 */
export function rewriteMarkdownImageSrcsForDisplay(md: string): string {
  return md.replace(
    /!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g,
    (full, alt: string, rawSrc: string) => {
      const src = rawSrc.trim();
      if (!isKbRelativeImagePath(src)) return full;
      return `![${alt}](${downloadUrl(src)})`;
    },
  );
}

function pathFromDownloadUrl(src: string): string | null {
  const raw = src.trim();
  if (!raw || !raw.includes("/api/download")) return null;
  try {
    const u = new URL(raw, "http://local.invalid");
    if (
      u.pathname.endsWith("/api/download") ||
      u.pathname === "/api/download" ||
      raw.includes("/api/download")
    ) {
      const path = u.searchParams.get("path");
      if (path) return path;
    }
  } catch {
    /* fall through */
  }
  const m = raw.match(/[?&]path=([^&]+)/);
  if (m) {
    try {
      return decodeURIComponent(m[1]);
    } catch {
      return m[1];
    }
  }
  return null;
}

/**
 * 把展示期 download URL 还原为相对路径，避免写回文档。
 * 仍含无法还原的 /api/download 或签名附件 URL 时抛错（对齐后端 sanitize）。
 */
export function restoreMarkdownImageSrcsForStorage(md: string): string {
  return md.replace(
    /!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g,
    (full, alt: string, rawSrc: string) => {
      const src = rawSrc.trim();
      const path = pathFromDownloadUrl(src);
      if (path != null) return `![${alt}](${path})`;
      if (
        src.includes("/api/download") ||
        src.includes("/api/attachments/signed/") ||
        src.includes("/api/media/grant/")
      ) {
        throw new Error(
          "知识库正文禁止写入 /api/download 或媒体授权绝对 URL，请使用相对路径",
        );
      }
      return full;
    },
  );
}
