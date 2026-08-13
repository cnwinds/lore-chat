/** 会话深链：conversation://{cid} 或 conversation://{cid}/{messageId} */

export const CONVERSATION_CID_RE = /^[a-f0-9]{12}$/i;

export type ConversationLinkTarget = {
  conversationId: string;
  messageId?: string;
};

/** 解析 href / 裸串是否为会话深链。 */
export function parseConversationHref(
  href: string | undefined | null,
): ConversationLinkTarget | null {
  const raw = (href || "").trim();
  if (!raw) return null;
  let rest = raw;
  if (/^conversation:\/\//i.test(rest)) {
    rest = rest.replace(/^conversation:\/\//i, "");
  } else if (/^lorechat:\/\/conversation\//i.test(rest)) {
    rest = rest.replace(/^lorechat:\/\/conversation\//i, "");
  } else {
    return null;
  }
  rest = rest.replace(/^\/*/, "");
  const hashIdx = rest.indexOf("#");
  let hashMsg: string | undefined;
  if (hashIdx >= 0) {
    hashMsg = rest.slice(hashIdx + 1).trim() || undefined;
    rest = rest.slice(0, hashIdx);
  }
  const [cidPart, ...msgParts] = rest.split("/");
  const cid = (cidPart || "").trim();
  if (!CONVERSATION_CID_RE.test(cid)) return null;
  const pathMsg = msgParts.join("/").trim() || undefined;
  const messageId = pathMsg || hashMsg;
  return messageId
    ? { conversationId: cid.toLowerCase(), messageId }
    : { conversationId: cid.toLowerCase() };
}

export function buildConversationHref(
  conversationId: string,
  messageId?: string,
): string {
  const cid = conversationId.trim().toLowerCase();
  if (messageId?.trim()) {
    return `conversation://${cid}/${messageId.trim()}`;
  }
  return `conversation://${cid}`;
}

/**
 * 遗留正文兼容：把历史里「会话：{cid} … 标题：…」改写成 conversation:// 链接。
 * 新产出应直接写协议链接（见 SYSTEM 原则）；此处不替代模型契约。
 */
export function linkifyConversationCitations(md: string): string {
  if (!md || !/会话/.test(md)) return md;
  let out = md.replace(
    /(📌\s*)?会话[：:]\s*(?:`)?([a-f0-9]{12})(?:`)?(?!\s*\()(?:\s*标题[：:]\s*([^\n]+?))?(?=\s*(?:时间[：:]|$|\n))/gi,
    (_full, pin: string | undefined, cid: string, title?: string) => {
      const label = (title || "").trim() || `会话 ${cid.slice(0, 6)}`;
      const prefix = pin || "";
      return `${prefix}[${label}](${buildConversationHref(cid)})`;
    },
  );
  out = out.replace(
    /(📌\s*)?会话[：:]\s*`([a-f0-9]{12})`/gi,
    (_full, pin: string | undefined, cid: string) => {
      const prefix = pin || "";
      return `${prefix}[会话 ${cid.slice(0, 6)}](${buildConversationHref(cid)})`;
    },
  );
  return out;
}
