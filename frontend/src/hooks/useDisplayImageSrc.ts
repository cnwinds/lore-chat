import { useEffect, useState } from "react";

/** download URL 或路径是否指向 SVG。 */
export function isSvgDisplaySrc(src: string): boolean {
  const raw = (src || "").trim();
  if (!raw) return false;
  try {
    const u = new URL(raw, "http://local.invalid");
    if (u.pathname.includes("/api/download")) {
      const path = u.searchParams.get("path") || "";
      return /\.svg$/i.test(path);
    }
  } catch {
    /* fall through */
  }
  return /\.svg(\?|#|$)/i.test(raw);
}

function withXmlEncodingDecl(svgText: string): string {
  const t = svgText.replace(/^\uFEFF/, "");
  if (/^\s*<\?xml/i.test(t)) return t;
  return `<?xml version="1.0" encoding="UTF-8"?>\n${t}`;
}

/**
 * SVG 经 /api/download 时部分浏览器对 Content-Disposition / 编码敏感，
 * 拉取正文后转 blob: URL，保证 <img> 能显示。
 * 返回 null 表示仍在加载（SVG），避免先闪破碎图。
 */
export function useDisplayImageSrc(src: string): string | null {
  const needsBlob = Boolean(src) && isSvgDisplaySrc(src);
  const [resolved, setResolved] = useState<string | null>(() =>
    needsBlob ? null : src || null,
  );

  useEffect(() => {
    if (!src) {
      setResolved(null);
      return;
    }
    if (!isSvgDisplaySrc(src)) {
      setResolved(src);
      return;
    }
    let objectUrl: string | null = null;
    let cancelled = false;
    setResolved(null);
    (async () => {
      try {
        const r = await fetch(src, { credentials: "include" });
        if (!r.ok) throw new Error(`svg fetch ${r.status}`);
        const text = withXmlEncodingDecl(await r.text());
        const blob = new Blob([text], { type: "image/svg+xml" });
        const url = URL.createObjectURL(blob);
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        objectUrl = url;
        setResolved(url);
      } catch {
        if (!cancelled) setResolved(src);
      }
    })();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [src]);

  return resolved;
}
