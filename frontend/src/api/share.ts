import { apiBase, openJson as apiFetch } from "../lib/httpTransport";
import type { ChatMessage } from "../types/chat";

export type ShareExpiryPreset = "permanent" | "1d" | "7d" | "30d" | "custom";

export type ShareLinkItem = {
  share_id: string;
  type: "conversation" | "doc";
  title: string;
  created_at: string;
  exp: string | null;
  revoked: boolean;
  view_count: number;
  options: { pin_version?: boolean; source_path?: string };
  url?: string | null;
};

export type CreateShareRequest =
  | {
      type: "conversation";
      conversation_id: string;
      title?: string;
      ttl_sec: number | null;
    }
  | {
      type: "doc";
      path: string;
      title?: string;
      ttl_sec: number | null;
      options?: { pin_version?: boolean };
    };

export type CreateShareResponse = ShareLinkItem & { url: string };

export type PublicConversationShare = {
  type: "conversation";
  title: string;
  exp: string | null;
  messages: ChatMessage[];
};

export type PublicDocShare = {
  type: "doc";
  title: string;
  exp: string | null;
  body: string;
  outline?: string[];
};

export type PublicSharePayload = PublicConversationShare | PublicDocShare;

export function ttlSecFromPreset(preset: ShareExpiryPreset, customExp?: string): number | null {
  if (preset === "permanent") return null;
  if (preset === "1d") return 86400;
  if (preset === "7d") return 7 * 86400;
  if (preset === "30d") return 30 * 86400;
  if (preset === "custom" && customExp) {
    const ms = Date.parse(customExp);
    if (!Number.isFinite(ms)) return null;
    const sec = Math.floor((ms - Date.now()) / 1000);
    if (sec < 60) return null;
    return sec;
  }
  return null;
}

export function createShare(body: CreateShareRequest) {
  return apiFetch<CreateShareResponse>("/api/shares", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function listShares() {
  return apiFetch<{ shares: ShareLinkItem[] }>("/api/shares");
}

export function revokeShare(shareId: string) {
  return apiFetch<{ ok: boolean }>(`/api/shares/${encodeURIComponent(shareId)}`, {
    method: "DELETE",
  });
}

/** 公开分享页：不带 cookie 也可访问 */
export function getPublicShare(shareId: string) {
  return fetch(`${apiBase()}/api/share/${encodeURIComponent(shareId)}`).then(async (res) => {
    if (res.status === 410) {
      throw new Error("分享链接已过期");
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const detail = (err as { detail?: string }).detail;
      throw new Error(typeof detail === "string" ? detail : "分享链接不存在或已失效");
    }
    return res.json() as Promise<PublicSharePayload>;
  });
}

export function parseSharePathname(pathname: string): string | null {
  const m = pathname.match(/^\/share\/([A-Za-z0-9_-]{16,64})$/);
  return m ? m[1] : null;
}
