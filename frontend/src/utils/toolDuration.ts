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
