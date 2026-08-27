import { putSettings } from "../../api";

/** 浏览器当前访问源，用作 Public Base URL（无尾斜杠）。 */
export function clientAccessOrigin(): string {
  if (typeof window === "undefined") return "";
  const { protocol, host } = window.location;
  if (!protocol || !host) return "";
  return `${protocol}//${host}`.replace(/\/$/, "");
}

/**
 * 首次加载且 Public Base URL 来自浏览器 fallback 时自动持久化。
 * 与 hydrate 分离，避免「读设置」路径隐含写盘。
 */
export async function ensurePublicBaseUrlOnLoad(
  publicBaseUrl: string,
  fromFallback: boolean,
): Promise<{ saved: boolean; message?: string }> {
  if (!fromFallback || !publicBaseUrl) return { saved: false };
  try {
    await putSettings({ public_base_url: publicBaseUrl });
    return {
      saved: true,
      message: "已根据当前访问地址自动填写并保存 Public Base URL",
    };
  } catch {
    return { saved: false };
  }
}
