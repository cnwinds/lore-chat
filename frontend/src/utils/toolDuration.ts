/**
 * 秒表锚点：优先已有 started_at_ms，否则解析服务端 tool `ts`。
 * 非法 ts 返回 undefined（勿用 Date.now()，否则切会话恢复会把秒表重置为 0）。
 */
export function resolveToolStartedAtMs(
  ts: string | undefined,
  existing?: number,
): number | undefined {
  if (typeof existing === "number" && Number.isFinite(existing)) {
    return existing;
  }
  if (typeof ts !== "string" || !ts) return undefined;
  const fromTs = Date.parse(ts);
  return Number.isFinite(fromTs) ? fromTs : undefined;
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
    if (block.started_at_ms != null) {
      const now = opts.nowMs ?? Date.now();
      return Math.max(0, now - block.started_at_ms);
    }
    return opts.liveElapsedMs;
  }
  return block.duration_ms;
}
