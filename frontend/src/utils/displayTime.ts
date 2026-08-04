/** 产品内所有展示时间均按中国标准时间（北京时间，UTC+8，无夏令时）。 */

export const DISPLAY_TIME_ZONE = "Asia/Shanghai";

const LOCALE = "zh-CN";

const NAIVE_ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

type Ymd = { y: number; m: number; d: number };

function partsInZone(
  date: Date,
  timeZone: string,
  includeTime: boolean,
): Record<string, string> {
  const opts: Intl.DateTimeFormatOptions = {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  };
  if (includeTime) {
    opts.hour = "2-digit";
    opts.minute = "2-digit";
    opts.second = "2-digit";
    opts.hour12 = false;
  }
  const parts = new Intl.DateTimeFormat("en-US", opts).formatToParts(date);
  const out: Record<string, string> = {};
  for (const p of parts) {
    if (p.type !== "literal") out[p.type] = p.value;
  }
  return out;
}

/** 解析后端/SSE 时间：无时区后缀的 ISO 视为北京时间墙钟。 */
export function parseStoredInstant(iso: string): Date | null {
  const trimmed = iso.trim();
  if (!trimmed) return null;
  let normalized = trimmed;
  if (NAIVE_ISO.test(trimmed) && !/(Z|[+-]\d{2}:\d{2})$/i.test(trimmed)) {
    normalized = `${trimmed}+08:00`;
  }
  const d = new Date(normalized);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function ymdInDisplayZone(date: Date): Ymd {
  const p = partsInZone(date, DISPLAY_TIME_ZONE, false);
  return {
    y: Number(p.year),
    m: Number(p.month),
    d: Number(p.day),
  };
}

function sameCalendarDay(a: Date, b: Date): boolean {
  const ya = ymdInDisplayZone(a);
  const yb = ymdInDisplayZone(b);
  return ya.y === yb.y && ya.m === yb.m && ya.d === yb.d;
}

/** 消息气泡旁 HH:mm（24 小时制）。 */
export function formatMessageTime(iso: string): string {
  const d = parseStoredInstant(iso);
  if (!d) return "";
  return d.toLocaleTimeString(LOCALE, {
    timeZone: DISPLAY_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** 月/日，用于来源芯片等。 */
export function formatMonthDay(iso: string): string {
  const d = parseStoredInstant(iso);
  if (!d) return "";
  return d.toLocaleDateString(LOCALE, {
    timeZone: DISPLAY_TIME_ZONE,
    month: "numeric",
    day: "numeric",
  });
}

/** 侧栏会话列表：今天显示时刻，否则月/日。 */
export function formatSidebarConversationTime(
  iso: string,
  now: Date = new Date(),
): string {
  const d = parseStoredInstant(iso);
  if (!d) return "";
  if (sameCalendarDay(d, now)) {
    return formatMessageTime(iso);
  }
  return formatMonthDay(iso);
}

/** 文档元数据等：yyyy-MM-dd HH:mm。 */
export function formatDisplayDateTime(iso: string): string {
  const d = parseStoredInstant(iso);
  if (!d) return "";
  const p = partsInZone(d, DISPLAY_TIME_ZONE, true);
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}`;
}

/** 客户端乐观时间戳，与后端 now_iso_seconds 语义一致（+08:00）。 */
export function nowIsoDisplay(): string {
  const d = new Date();
  const p = partsInZone(d, DISPLAY_TIME_ZONE, true);
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}+08:00`;
}

/** 会话分组边界用的「今日 0 点」比较（按北京时间日历）。 */
export function isSameDisplayDay(iso: string, ref: Date): boolean {
  const d = parseStoredInstant(iso);
  if (!d) return false;
  return sameCalendarDay(d, ref);
}

export function displayYmd(iso: string): Ymd | null {
  const d = parseStoredInstant(iso);
  if (!d) return null;
  return ymdInDisplayZone(d);
}
