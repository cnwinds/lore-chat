import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
  listRoleScheduleRuns,
  type RoleSchedule,
  type RoleScheduleRun,
} from "../../api";
import { formatRoleListTime } from "../../utils/displayTime";
import {
  defaultScheduleTiming,
  timingFromSchedule,
  type ScheduleTiming,
} from "../../utils/scheduleTiming";
import { ScheduleTimingFields } from "./ScheduleTimingFields";

type Props = {
  open: boolean;
  roleId: string;
  schedule: RoleSchedule | null;
  saving?: boolean;
  onClose: () => void;
  onSave: (body: {
    prompt: string;
    timing: ScheduleTiming;
    enabled: boolean;
  }) => void;
  onDelete?: () => void;
};

export function RoutineDetailModal({
  open,
  roleId,
  schedule,
  saving = false,
  onClose,
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
    if (!open) return;
    setPrompt(schedule?.prompt || "");
    setTiming(
      schedule ? timingFromSchedule(schedule) : defaultScheduleTiming(),
    );
    setEnabled(schedule?.enabled ?? true);
  }, [open, schedule]);

  useEffect(() => {
    if (!open || !schedule) {
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
  }, [open, roleId, schedule]);

  if (!open) return null;

  return createPortal(
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <form
        className="modal-panel role-settings-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="routine-detail-title"
        onClick={(e) => e.stopPropagation()}
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
        <div className="role-settings-head">
          <h3 id="routine-detail-title">
            {creating ? "创建例行任务" : "例行任务"}
          </h3>
          <button
            type="button"
            className="role-settings-close"
            onClick={onClose}
            aria-label="关闭"
          >
            ×
          </button>
        </div>
        <div className="role-settings-body">
          <label className="settings-field">
            <span>任务说明</span>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={4}
              placeholder="定时发送的提示词，例如：汇总今日进展"
              disabled={saving}
            />
          </label>
          <ScheduleTimingFields
            value={timing}
            onChange={setTiming}
            disabled={saving}
          />
          <label className="settings-field settings-field--checkbox">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              disabled={saving}
            />
            <span>启用</span>
          </label>
          {!creating ? (
            <section className="role-routine-history">
              <h4>执行历史</h4>
              {schedule.last_run_at || schedule.next_run_at ? (
                <p className="settings-group-hint">
                  {schedule.last_run_at
                    ? `上次 ${formatRoleListTime(schedule.last_run_at)}`
                    : "尚未执行"}
                  {schedule.next_run_at
                    ? ` · 下次 ${formatRoleListTime(schedule.next_run_at)}`
                    : ""}
                </p>
              ) : null}
              {loadingRuns ? (
                <p className="settings-group-hint">加载历史…</p>
              ) : runs.length === 0 ? (
                <p className="settings-group-hint">还没有执行记录</p>
              ) : (
                <ul className="role-routine-run-list">
                  {runs.map((run) => (
                    <li key={run.turn_id} className="role-routine-run">
                      <div className="role-routine-run-meta">
                        {formatRoleListTime(run.started_at)}
                        {run.status === "complete"
                          ? ""
                          : ` · ${run.status}`}
                      </div>
                      <div className="role-routine-run-summary">
                        {run.summary || "（无摘要）"}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ) : null}
        </div>
        <div className="role-settings-foot">
          {schedule && onDelete ? (
            <button
              type="button"
              className="btn-danger"
              onClick={onDelete}
              disabled={saving}
            >
              删除
            </button>
          ) : (
            <div className="role-settings-foot-spacer" />
          )}
          <button type="button" onClick={onClose} disabled={saving}>
            取消
          </button>
          <button
            type="submit"
            className="btn-primary"
            disabled={saving || !prompt.trim()}
          >
            {saving ? "保存中…" : creating ? "创建" : "保存"}
          </button>
        </div>
      </form>
    </div>,
    document.body,
  );
}
