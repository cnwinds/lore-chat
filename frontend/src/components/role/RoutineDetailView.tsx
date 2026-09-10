import { useEffect, useState } from "react";
import {
  listRoleScheduleRuns,
  type RoleSchedule,
  type RoleScheduleRun,
} from "../../api";
import { formatRoutineRunTime } from "../../utils/displayTime";
import {
  defaultScheduleTiming,
  timingFromSchedule,
  type ScheduleTiming,
} from "../../utils/scheduleTiming";
import { ScheduleTimingFields } from "./ScheduleTimingFields";

type Props = {
  roleId: string;
  schedule: RoleSchedule | null;
  saving?: boolean;
  onSave: (body: {
    prompt: string;
    timing: ScheduleTiming;
    enabled: boolean;
  }) => void;
  onDelete?: () => void;
};

function runStatusMark(status: string): { label: string; ok: boolean } {
  if (status === "complete") return { label: "完成", ok: true };
  if (status === "running" || status === "started") {
    return { label: "进行中", ok: false };
  }
  return { label: status || "未完成", ok: false };
}

export function RoutineDetailView({
  roleId,
  schedule,
  saving = false,
  onSave,
  onDelete,
}: Props) {
  const creating = !schedule;
  const [prompt, setPrompt] = useState("");
  const [timing, setTiming] = useState<ScheduleTiming>(defaultScheduleTiming);
  const [enabled, setEnabled] = useState(true);
  const [runs, setRuns] = useState<RoleScheduleRun[]>([]);
  const [loadingRuns, setLoadingRuns] = useState(false);

  useEffect(() => {
    setPrompt(schedule?.prompt || "");
    setTiming(
      schedule ? timingFromSchedule(schedule) : defaultScheduleTiming(),
    );
    setEnabled(schedule?.enabled ?? true);
  }, [schedule]);

  useEffect(() => {
    if (!schedule) {
      setRuns([]);
      return;
    }
    let cancelled = false;
    setLoadingRuns(true);
    void listRoleScheduleRuns(roleId, schedule.id)
      .then((res) => {
        if (!cancelled) setRuns(res.runs);
      })
      .catch(() => {
        if (!cancelled) setRuns([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingRuns(false);
      });
    return () => {
      cancelled = true;
    };
  }, [roleId, schedule]);

  return (
    <form
      className="role-routine-detail"
      aria-labelledby="routine-detail-title"
      onSubmit={(e) => {
        e.preventDefault();
        if (!prompt.trim()) return;
        onSave({
          prompt: prompt.trim(),
          timing,
          enabled,
        });
      }}
    >
      <div className="role-routine-detail-head">
        <h3 id="routine-detail-title">
          {creating ? "创建例行任务" : "例行任务"}
        </h3>
        <div className="role-routine-detail-actions">
          <button
            type="button"
            role="switch"
            aria-checked={enabled}
            className={`role-routine-switch${enabled ? " is-on" : ""}`}
            onClick={() => setEnabled((v) => !v)}
            disabled={saving}
          >
            <span className="role-routine-switch-track" aria-hidden>
              <span className="role-routine-switch-knob" />
            </span>
            启用
          </button>
          {schedule && onDelete ? (
            <button
              type="button"
              className="role-routine-text-btn role-routine-text-btn--danger"
              onClick={onDelete}
              disabled={saving}
            >
              删除
            </button>
          ) : null}
        </div>
      </div>

      <div className="role-routine-detail-body">
        <label className="role-config-label">
          <span>任务说明</span>
          <textarea
            className="role-config-textarea"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={6}
            placeholder="定时发给这个角色的提示词，例如：汇总今日进展"
            disabled={saving}
          />
        </label>
        <ScheduleTimingFields
          value={timing}
          onChange={setTiming}
          disabled={saving}
        />
        {!creating ? (
          <section className="role-routine-history" aria-labelledby="routine-history-title">
            <h4 id="routine-history-title">执行历史</h4>
            {loadingRuns ? (
              <p className="role-routine-history-empty">加载历史…</p>
            ) : runs.length === 0 ? (
              <p className="role-routine-history-empty">还没有执行记录</p>
            ) : (
              <ul className="role-routine-run-list">
                {runs.map((run) => {
                  const mark = runStatusMark(run.status);
                  return (
                    <li key={run.turn_id} className="role-routine-run">
                      <div className="role-routine-run-row">
                        <span className="role-routine-run-time">
                          {formatRoutineRunTime(run.started_at)}
                        </span>
                        <span
                          className={`role-routine-run-mark${mark.ok ? " is-ok" : ""}`}
                          title={mark.label}
                        >
                          {mark.ok ? "✓" : "·"}
                        </span>
                      </div>
                      {run.summary ? (
                        <div className="role-routine-run-summary">
                          {run.summary}
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        ) : null}
      </div>

      <div className="role-routine-detail-foot">
        <button
          type="submit"
          className="role-config-primary-btn"
          disabled={saving || !prompt.trim()}
        >
          {saving ? "保存中…" : creating ? "创建" : "保存"}
        </button>
      </div>
    </form>
  );
}
