/** 用量趋势图与按模型列表的展示纯函数。 */

export type UsageSortable = {
  model: string;
  total_tokens: number;
  calls: number;
};

export function bucketLabel(bucket: string | undefined, granularity: string): string {
  if (!bucket) return "—";
  if (granularity === "hour" && bucket.length >= 13) {
    const month = Number(bucket.slice(5, 7));
    const day = Number(bucket.slice(8, 10));
    const hour = bucket.slice(11, 13);
    return `${month}月${day}日 ${hour}时`;
  }
  if (granularity === "day" && bucket.length >= 10) {
    const month = Number(bucket.slice(5, 7));
    const day = Number(bucket.slice(8, 10));
    return `${month}月${day}日`;
  }
  if (granularity === "week") {
    const m = /^(\d{4})-W(\d{2})$/.exec(bucket);
    if (m) return `${m[1]}年第${Number(m[2])}周`;
    return bucket;
  }
  if (granularity === "month" && bucket.length >= 7) {
    return `${bucket.slice(0, 4)}年${Number(bucket.slice(5, 7))}月`;
  }
  return bucket;
}

export function sortModelsByUsage<T extends UsageSortable>(rows: T[]): T[] {
  return [...rows].sort(
    (a, b) =>
      b.total_tokens - a.total_tokens ||
      b.calls - a.calls ||
      a.model.localeCompare(b.model, "zh-CN"),
  );
}

/** 默认对准最近一条有用量的柱；全空则落在最后一根。 */
export function defaultTrendIndex(
  buckets: Array<{ total_tokens?: number; calls?: number }>,
): number {
  if (buckets.length === 0) return 0;
  for (let i = buckets.length - 1; i >= 0; i--) {
    const tokens = buckets[i].total_tokens || 0;
    const calls = buckets[i].calls || 0;
    if (tokens > 0 || calls > 0) return i;
  }
  return buckets.length - 1;
}

export function trendAxisEnds(
  buckets: Array<{ bucket?: string }>,
  granularity: string,
): { start: string; end: string } | null {
  if (buckets.length === 0) return null;
  const start = bucketLabel(buckets[0].bucket, granularity);
  const end = bucketLabel(buckets[buckets.length - 1].bucket, granularity);
  return { start, end };
}

export function stepTrendIndex(current: number, delta: number, length: number): number {
  if (length <= 0) return 0;
  return Math.min(length - 1, Math.max(0, current + delta));
}
