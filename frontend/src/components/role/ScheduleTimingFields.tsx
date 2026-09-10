import {
  SCHEDULE_KIND_OPTIONS,
  WEEKDAY_LABELS,
  applyScheduleKind,
  parseTimeValue,
  timingTimeValue,
  type ScheduleKind,
  type ScheduleTiming,
} from "../../utils/scheduleTiming";

type Props = {
  value: ScheduleTiming;
  onChange: (next: ScheduleTiming) => void;
  disabled?: boolean;
  idPrefix?: string;
};

export function ScheduleTimingFields({
  value,
  onChange,
  disabled = false,
  idPrefix = "sched-timing",
}: Props) {
  const kindSelectId = `${idPrefix}-kind`;
  const timeId = `${idPrefix}-time`;

  function setKind(kind: ScheduleKind) {
    onChange(applyScheduleKind(value, kind));
  }

  function setClock(raw: string) {
    onChange({ ...value, ...parseTimeValue(raw) });
  }

  function toggleWeekday(day: number) {
    const current = new Set(value.weekdays ?? [0]);
    if (current.has(day)) {
      current.delete(day);
    } else {
      current.add(day);
    }
    const next = [...current].sort((a, b) => a - b);
    onChange({ ...value, weekdays: next.length ? next : [day] });
  }

  const showClock =
    value.kind === "daily" ||
    value.kind === "weekdays" ||
    value.kind === "weekly" ||
    value.kind === "monthly";

  return (
    <div className="schedule-timing">
      <label className="role-config-label" htmlFor={kindSelectId}>
        <span>何时运行</span>
        <select
          id={kindSelectId}
          className="role-config-input"
          value={value.kind}
          disabled={disabled}
          onChange={(e) => setKind(e.target.value as ScheduleKind)}
        >
          {SCHEDULE_KIND_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>

      {value.kind === "hourly" ? (
        <label className="role-config-label">
          <span>在每小时的第几分</span>
          <input
            type="number"
            className="role-config-input"
            min={0}
            max={59}
            step={1}
            value={value.minute ?? 0}
            disabled={disabled}
            onChange={(e) =>
              onChange({
                ...value,
                minute: Math.min(59, Math.max(0, Number(e.target.value) || 0)),
              })
            }
          />
        </label>
      ) : null}

      {showClock ? (
        <label className="role-config-label" htmlFor={timeId}>
          <span>时间（北京时间）</span>
          <input
            id={timeId}
            type="time"
            className="role-config-input"
            value={timingTimeValue(value)}
            disabled={disabled}
            onChange={(e) => setClock(e.target.value)}
          />
        </label>
      ) : null}

      {value.kind === "weekly" ? (
        <div className="schedule-timing-weekdays">
          <span className="schedule-timing-weekdays-label">星期</span>
          <div className="schedule-timing-weekdays-row">
            {WEEKDAY_LABELS.map((label, day) => {
              const on = (value.weekdays ?? [0]).includes(day);
              return (
                <button
                  key={label}
                  type="button"
                  className={`schedule-timing-day${on ? " schedule-timing-day--on" : ""}`}
                  disabled={disabled}
                  aria-pressed={on}
                  onClick={() => toggleWeekday(day)}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      {value.kind === "monthly" ? (
        <label className="role-config-label">
          <span>每月第几天</span>
          <input
            type="number"
            className="role-config-input"
            min={1}
            max={31}
            step={1}
            value={value.day_of_month ?? 1}
            disabled={disabled}
            onChange={(e) =>
              onChange({
                ...value,
                day_of_month: Math.min(
                  31,
                  Math.max(1, Number(e.target.value) || 1),
                ),
              })
            }
          />
        </label>
      ) : null}

      {value.kind === "interval" ? (
        <label className="role-config-label">
          <span>间隔（小时）</span>
          <input
            type="number"
            className="role-config-input"
            min={0.5}
            step={0.5}
            value={value.interval_hours ?? 24}
            disabled={disabled}
            onChange={(e) =>
              onChange({
                ...value,
                interval_hours: Number(e.target.value) || 24,
              })
            }
          />
        </label>
      ) : null}

      {value.kind === "cron" ? (
        <label className="role-config-label">
          <span>Cron（分 时 日 月 周）</span>
          <input
            type="text"
            className="role-config-input"
            value={value.cron ?? ""}
            disabled={disabled}
            placeholder="0 9 * * 1-5"
            onChange={(e) => onChange({ ...value, cron: e.target.value })}
            spellCheck={false}
          />
        </label>
      ) : null}

      <p className="schedule-timing-hint">按北京时间触发；有进行中回合则顺延。</p>
    </div>
  );
}
