export const CONVERSATION_CID_RE = /^[a-f0-9]{12}$/i;

export type LoreHref =
  | { kind: "conversation"; conversationId: string; messageId?: string }
  | { kind: "kb"; path: string; isDir: boolean }
  | { kind: "memory" };

function decodeSegment(seg: string): string {
  try {
    return decodeURIComponent(seg);
  } catch {
    return seg;
  }
}

function splitLorePath(rest: string): { segments: string[]; hadTrailingSlash: boolean } {
  const hadTrailingSlash = /\/$/.test(rest);
  const withoutTrailing = rest.replace(/\/+$/, "");
  if (!withoutTrailing) return { segments: [], hadTrailingSlash };
  return {
    segments: withoutTrailing.split("/").map(decodeSegment),
    hadTrailingSlash,
  };
}

function isUnsafeKbPath(segments: string[]): boolean {
  if (segments.length === 0) return true;
  return segments.some((s) => s === ".." || s === ".");
}

function loreConversationTarget(
  cidPart: string,
  msgPart: string,
): Extract<LoreHref, { kind: "conversation" }> | null {
  const cid = cidPart.trim();
  if (!cid || !CONVERSATION_CID_RE.test(cid)) return null;
  const msg = msgPart.trim();
  if (msg) {
    return { kind: "conversation", conversationId: cid.toLowerCase(), messageId: msg };
  }
  return { kind: "conversation", conversationId: cid.toLowerCase() };
}

function parseLoreConversation(
  segments: string[],
): Extract<LoreHref, { kind: "conversation" }> | null {
  if (segments[0] !== "conversations") return null;
  const kind = segments[1];
  if (kind === "dm") {
    const roleId = (segments[2] || "").trim();
    if (!roleId) return null;
    if (segments.length > 5) return null;
    return loreConversationTarget(segments[3] || "", segments[4] || "");
  }
  if (kind === "rooms") {
    if (segments.length > 4) return null;
    return loreConversationTarget(segments[2] || "", segments[3] || "");
  }
  if (kind === "channels") {
    const inst = (segments[2] || "").trim();
    if (!inst) return null;
    if (segments.length > 5) return null;
    return loreConversationTarget(segments[3] || "", segments[4] || "");
  }
  return null;
}

/** 解析 lore:// 地址（会话 / 知识库 / 记忆）；非法或未知命名空间返回 null。 */
export function parseLoreHref(href: string | undefined | null): LoreHref | null {
  const raw = (href || "").trim();
  if (!/^lore:\/\//i.test(raw)) return null;

  let rest = raw.replace(/^lore:\/\//i, "");
  rest = rest.replace(/^\/*/, "");
  if (!rest) return null;

  let hashMsg: string | undefined;
  const hashIdx = rest.indexOf("#");
  if (hashIdx >= 0) {
    hashMsg = rest.slice(hashIdx + 1).trim() || undefined;
    rest = rest.slice(0, hashIdx);
  }

  const { segments, hadTrailingSlash } = splitLorePath(rest);
  if (segments.length === 0) return null;

  const head = segments[0];
  if (head === "conversations") {
    const conv = parseLoreConversation(segments);
    if (!conv) return null;
    if (hashMsg && !conv.messageId) {
      return { ...conv, messageId: hashMsg };
    }
    return conv;
  }

  if (head === "kb") {
    const kbSegments = segments.slice(1);
    if (isUnsafeKbPath(kbSegments)) return null;
    const path = kbSegments.join("/");
    const isDir = hadTrailingSlash;
    return { kind: "kb", path, isDir };
  }

  if (head === "memory") {
    return { kind: "memory" };
  }

  return null;
}
