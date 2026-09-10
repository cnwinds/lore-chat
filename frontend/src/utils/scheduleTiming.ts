export type ScheduleKind =
  | "interval"
  | "hourly"
  | "daily"
  | "weekdays"
  | "weekly"
  | "monthly"
  | "cron";

export type ScheduleTiming = {
  kind: ScheduleKind;
  interval_hours?: number;
  hour?: number;
  minute?: number;
  weekdays?: number[];
  day_of_month?: number;
  cron?: string;
};

export const SCHEDULE_KIND_OPTIONS: { value: ScheduleKind; label: string }[] = [
  { value: "hourly", label: "每小时" },
  { value: "daily", label: "每天" },
  { value: "weekdays", label: "工作日" },
  { value: "weekly", label: "每周" },
  { value: "monthly", label: "每月" },
  { value: "interval", label: "间隔" },
  { value: "cron", label: "高级…" },
];

export const WEEKDAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"] as const;

export function defaultScheduleTiming(): ScheduleTiming {
  return { kind: "daily", hour: 9, minute: 0 };
}

export function timingFromSchedule(s: {
  timing?: ScheduleTiming;
  interval_hours?: number;
}): ScheduleTiming {
  if (s.timing?.kind) return s.timing;
  return {
    kind: "interval",
    interval_hours: s.interval_hours ?? 24,
  };
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

export function timingTimeValue(t: ScheduleTiming): string {
  return `${pad2(t.hour ?? 9)}:${pad2(t.minute ?? 0)}`;
}

export function parseTimeValue(value: string): { hour: number; minute: number } {
  const [h, m] = value.split(":");
  const hour = Math.min(23, Math.max(0, Number(h) || 0));
  const minute = Math.min(59, Math.max(0, Number(m) || 0));
  return { hour, minute };
}

export function applyScheduleKind(
  prev: ScheduleTiming,
  kind: ScheduleKind,
): ScheduleTiming {
  if (kind === "interval") {
    return { kind, interval_hours: prev.interval_hours ?? 24 };
  }
  if (kind === "hourly") {
    return { kind, minute: prev.minute ?? 0 };
  }
  if (kind === "cron") {
    return { kind, cron: prev.cron || "0 9 * * 1-5" };
  }
  const hour = prev.hour ?? 9;
  const minute = prev.minute ?? 0;
  if (kind === "weekly") {
    return {
      kind,
      hour,
      minute,
      weekdays: prev.weekdays?.length ? prev.weekdays : [0],
    };
  }
  if (kind === "monthly") {
    return {
      kind,
      hour,
      minute,
      day_of_month: prev.day_of_month ?? 1,
    };
  }
  return { kind, hour, minute };
}
