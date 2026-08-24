import { apiBase, openJson as apiFetch } from "../lib/httpTransport";
import type { ChatMessage } from "../types/chat";

export type ShareExpiryPreset = "permanent" | "1d" | "7d" | "30d" | "custom";

export type ShareRecentView = {
  ts: string;
  referer?: string;
};

export type ShareLinkItem = {
  share_id: string;
  type: "conversation" | "doc";
  title: string;
  created_at: string;
  exp: string | null;
  revoked: boolean;
  view_count: number;
  last_viewed_at?: string | null;
  recent_views?: ShareRecentView[];
  options: {
    pin_version?: boolean;
    conversation_id?: string;
    source_path?: string;
    has_password?: boolean;
    message_ids?: string[];
    message_count?: number;
  };
  url?: string | null;
};

export type CreateShareRequest =
  | {
      type: "conversation";
      conversation_id: string;
      title?: string;
      ttl_sec: number | null;
      message_ids?: string[];
      password?: string;
      options?: { pin_version?: boolean };
    }
  | {
      type: "doc";
      path: string;
      title?: string;
      ttl_sec: number | null;
      password?: string;
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

export const SHARE_PASSWORD_REQUIRED = "SHARE_PASSWORD_REQUIRED";
export const SHARE_PASSWORD_INVALID = "SHARE_PASSWORD_INVALID";

export function shareUnlockStorageKey(shareId: string): string {
  return `lorechat_share_unlock:${shareId}`;
}

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
export class SharePublicError extends Error {
  status: number;
  code?: string;
  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "SharePublicError";
    this.status = status;
    this.code = code;
  }
}

function parseShareDetail(err: unknown): { message: string; code?: string } {
  const detail = (err as { detail?: unknown })?.detail;
  if (typeof detail === "string") return { message: detail };
  if (detail && typeof detail === "object") {
    const d = detail as { code?: string; message?: string };
    return {
      message: typeof d.message === "string" ? d.message : "请求失败",
      code: typeof d.code === "string" ? d.code : undefined,
    };
  }
  return { message: "请求失败" };
}

export function getPublicShare(shareId: string, unlockToken?: string | null) {
  const headers: Record<string, string> = {};
  if (unlockToken) headers["X-Share-Unlock"] = unlockToken;
  return fetch(`${apiBase()}/api/share/${encodeURIComponent(shareId)}`, {
    headers,
    credentials: "include",
  }).then(async (res) => {
    if (res.status === 410) {
      throw new SharePublicError(410, "分享链接已过期");
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const { message, code } = parseShareDetail(err);
      throw new SharePublicError(
        res.status,
        message || "分享链接不存在或已失效",
        code,
      );
    }
    return res.json() as Promise<PublicSharePayload>;
  });
}

export function unlockShare(shareId: string, password: string) {
  return fetch(`${apiBase()}/api/share/${encodeURIComponent(shareId)}/unlock`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
    credentials: "include",
  }).then(async (res) => {
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const { message, code } = parseShareDetail(err);
      throw new SharePublicError(
        res.status,
        message || "解锁失败",
        code,
      );
    }
    return res.json() as Promise<{ ok: boolean; unlock_token: string; ttl_sec: number }>;
  });
}

export function parseSharePathname(pathname: string): string | null {
  const m = pathname.match(/^\/share\/([A-Za-z0-9_-]{16,64})$/);
  return m ? m[1] : null;
}
