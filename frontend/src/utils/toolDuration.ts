/**
 * 秒表锚点：优先已有 started_at_ms，否则按北京时间解析服务端 tool `ts`。
 * 落在未来的锚点视为无效（常见于把北京墙钟当 UTC 解析），勿用 Date.now()
 * 在每次合并时重打，否则切会话恢复会把秒表重置为 0。
 */

import { parseStoredInstant } from "./displayTime";

/** 服务器/浏览器时钟允许的超前量；8 小时时区误解析不在此列。 */
export const START_CLOCK_SKEW_MS = 15_000;

export function isUsableStartMs(
  value: number | undefined,
  nowMs: number,
): value is number {
  return (
    typeof value === "number" &&
    Number.isFinite(value) &&
    value <= nowMs + START_CLOCK_SKEW_MS
  );
}

function parseTsMs(ts: string | undefined): number | undefined {
  if (typeof ts !== "string" || !ts) return undefined;
  const fromTs = parseStoredInstant(ts)?.getTime();
  return typeof fromTs === "number" && Number.isFinite(fromTs) ? fromTs : undefined;
}

export function resolveToolStartedAtMs(
  ts: string | undefined,
  existing?: number,
  nowMs: number = Date.now(),
): number | undefined {
  if (isUsableStartMs(existing, nowMs)) return existing;
  const fromTs = parseTsMs(ts);
  return isUsableStartMs(fromTs, nowMs) ? fromTs : undefined;
}

/**
 * 运行中工具的秒表原点：已有可用锚点则用，否则在 live 路径用 now 盖一次。
 * 完成态不需要原点。
 */
export function stampRunningStartedAtMs(
  block: { ts?: string; started_at_ms?: number; status?: string },
  nowMs: number = Date.now(),
): number | undefined {
  const resolved = resolveToolStartedAtMs(block.ts, block.started_at_ms, nowMs);
  if (resolved != null) return resolved;
  if (block.status === "running") return nowMs;
  return undefined;
}

/** 工具块展示用耗时：运行中按本工具起点计秒，完成后用服务端 duration_ms。 */
export function toolDisplayDurationMs(
  block: {
    status: string;
    duration_ms?: number;
    started_at_ms?: number;
  },
  opts: { nowMs?: number; liveElapsedMs?: number } = {},
): number | undefined {
  if (block.status === "running") {
    const now = opts.nowMs ?? Date.now();
    if (isUsableStartMs(block.started_at_ms, now)) {
      return Math.max(0, now - block.started_at_ms);
    }
    return opts.liveElapsedMs;
  }
  return block.duration_ms;
}

/** 思考块展示用耗时：进行中按起点秒表，结束后用 duration_ms。 */
export function thinkDisplayDurationMs(
  block: {
    duration_ms?: number;
    started_at_ms?: number;
    ts?: string;
  },
  opts: { nowMs?: number; isLive?: boolean } = {},
): number | undefined {
  if (block.duration_ms != null) return block.duration_ms;
  if (!opts.isLive) return undefined;
  const now = opts.nowMs ?? Date.now();
  const started = resolveToolStartedAtMs(block.ts, block.started_at_ms, now);
  if (started == null) return undefined;
  return Math.max(0, now - started);
}
