/** HTTP / SSE 传输：credentials、401、分帧（与领域 endpoint 分离）。 */

import type { ChatStreamEvent } from "../types/chat";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export type ApiError = Error & {
  status?: number;
  pathExists?: PathExistsDetail;
};

export type PathExistsDetail = {
  code: "PATH_EXISTS";
  path: string;
  message: string;
  suggested_filename: string;
};

export function apiBase(): string {
  return BASE;
}

function raiseUnauthorized(status: number): void {
  if (status === 401) {
    window.dispatchEvent(new CustomEvent("auth:unauthorized"));
  }
}

export function isDemoReadOnlyError(body: unknown): boolean {
  if (!body || typeof body !== "object") return false;
  const record = body as Record<string, unknown>;
  if (record.code === "demo_read_only") return true;
  const detail = record.detail;
  return (
    !!detail &&
    typeof detail === "object" &&
    (detail as Record<string, unknown>).code === "demo_read_only"
  );
}

export async function openJson<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    credentials: "include",
    ...init,
  });
  if (!r.ok) {
    let detail = r.statusText;
    let pathExists: PathExistsDetail | undefined;
    let parsedBody: unknown;
    try {
      parsedBody = await r.json();
      const body = parsedBody as Record<string, unknown>;
      if (
        r.status === 409 &&
        body.detail &&
        typeof body.detail === "object" &&
        (body.detail as PathExistsDetail).code === "PATH_EXISTS"
      ) {
        pathExists = body.detail as PathExistsDetail;
        detail = pathExists.message;
      } else {
        detail =
          typeof body.detail === "string"
            ? body.detail
            : typeof body.message === "string"
              ? body.message
              : JSON.stringify(body);
      }
    } catch {
      try {
        detail = (await r.text()) || detail;
      } catch {
        /* ignore */
      }
    }
    if (r.status === 403 && isDemoReadOnlyError(parsedBody)) {
      window.dispatchEvent(new CustomEvent("demo:read-only"));
    }
    const err = new Error(detail || `请求失败 (${r.status})`) as ApiError;
    err.status = r.status;
    err.pathExists = pathExists;
    raiseUnauthorized(r.status);
    throw err;
  }
  return r.json() as Promise<T>;
}

export async function openSse(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const { headers, ...rest } = init ?? {};
  const r = await fetch(`${BASE}${path}`, {
    credentials: "include",
    ...rest,
    headers: {
      Accept: "text/event-stream",
      ...(headers as Record<string, string> | undefined),
    },
  });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = (await r.text()) || detail;
    } catch {
      /* ignore */
    }
    const err = new Error(detail || `请求失败 (${r.status})`) as ApiError;
    err.status = r.status;
    raiseUnauthorized(r.status);
    throw err;
  }
  if (!r.body) {
    throw new Error("响应缺少可读流");
  }
  return r;
}

export async function* readSseResponse(
  r: Response,
): AsyncGenerator<ChatStreamEvent> {
  if (!r.body) {
    throw new Error("响应缺少可读流");
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  function parseEventBlock(part: string): ChatStreamEvent | undefined {
    if (!part.trim()) return undefined;
    const lines = part.split("\n");
    const eventLine = lines.find((l) => l.startsWith("event: "));
    const dataLine = lines.find((l) => l.startsWith("data: "));
    if (!eventLine || !dataLine) {
      console.warn("跳过无法识别的 SSE 事件块", part);
      return undefined;
    }
    try {
      return {
        event: eventLine.slice(7).trim(),
        data: JSON.parse(dataLine.slice(6)) as Record<string, unknown>,
      };
    } catch (err) {
      console.warn("跳过无法解析的 SSE 事件", err, dataLine);
      return undefined;
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        const evt = parseEventBlock(part);
        if (evt) yield evt;
      }
    }

    buffer += decoder.decode();
    if (buffer.trim()) {
      const evt = parseEventBlock(buffer);
      if (evt) yield evt;
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      /* ignore */
    }
  }
}
