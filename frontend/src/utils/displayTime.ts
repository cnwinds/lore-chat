/** 产品内所有展示时间均按中国标准时间（北京时间，UTC+8，无夏令时）。 */

export const DISPLAY_TIME_ZONE = "Asia/Shanghai";

const LOCALE = "zh-CN";

const NAIVE_ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;
const WALL_CLOCK = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/;

type Ymd = { y: number; m: number; d: number };

function pad2(v: string): string {
  return v.length === 1 ? `0${v}` : v;
}

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
  if (WALL_CLOCK.test(trimmed)) {
    const d = new Date(`${trimmed.replace(" ", "T")}+08:00`);
    return Number.isNaN(d.getTime()) ? null : d;
  }
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

function formatClockHm(d: Date): string {
  return d.toLocaleTimeString(LOCALE, {
    timeZone: DISPLAY_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** `M月D日 HH:mm`；跨年带年份。 */
function formatDateAndTime(d: Date, now: Date): string {
  const ymd = ymdInDisplayZone(d);
  const today = ymdInDisplayZone(now);
  const time = formatClockHm(d);
  if (ymd.y !== today.y) {
    return `${ymd.y}年${ymd.m}月${ymd.d}日 ${time}`;
  }
  return `${ymd.m}月${ymd.d}日 ${time}`;
}

/**
 * 消息气泡旁时间（24 小时制）。
 * 当天仅 HH:mm；跨日（翻出旧对话继续聊）带上日期。
 */
export function formatMessageTime(
  iso: string,
  now: Date = new Date(),
): string {
  const d = parseStoredInstant(iso);
  if (!d) return "";
  if (sameCalendarDay(d, now)) {
    return formatClockHm(d);
  }
  return formatDateAndTime(d, now);
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

/** 侧栏会话列表：始终显示日期 + 时刻（跨年带年份）。 */
export function formatSidebarConversationTime(
  iso: string,
  now: Date = new Date(),
): string {
  const d = parseStoredInstant(iso);
  if (!d) return "";
  return formatDateAndTime(d, now);
}

/** 文档元数据等：`YYYY-MM-DD HH:mm:ss`（已是该格式则原样返回）。 */
export function formatDisplayDateTime(iso: string): string {
  const trimmed = iso.trim();
  if (WALL_CLOCK.test(trimmed)) return trimmed;
  const isoWall = trimmed.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})/);
  if (isoWall) {
    return `${isoWall[1]} ${isoWall[2]}`;
  }
  const d = parseStoredInstant(trimmed);
  if (!d) return "";
  const p = partsInZone(d, DISPLAY_TIME_ZONE, true);
  return `${p.year}-${p.month}-${p.day} ${pad2(p.hour)}:${pad2(p.minute)}:${pad2(p.second)}`;
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
