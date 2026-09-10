import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
  createRoleSchedule,
  deleteRole,
  deleteRoleSchedule,
  listRoleSchedules,
  updateRole,
  updateRoleSchedule,
  type RoleSchedule,
  type RoleSummary,
} from "../api";
import { ScheduleTimingFields } from "./role/ScheduleTimingFields";
import { avatarStorageRef } from "../utils/kbImageUrls";
import {
  defaultScheduleTiming,
  type ScheduleTiming,
} from "../utils/scheduleTiming";

type Props = {
  role: RoleSummary;
  open: boolean;
  onClose: () => void;
  onSaved: (role: RoleSummary) => void;
  onDeleted?: () => void;
};

export function RoleSettingsModal({
  role,
  open,
  onClose,
  onSaved,
  onDeleted,
}: Props) {
  const [name, setName] = useState(role.name);
  const [systemPrompt, setSystemPrompt] = useState(role.system_prompt || "");
  const [avatar, setAvatar] = useState(role.avatar || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [schedules, setSchedules] = useState<RoleSchedule[]>([]);
  const [schedPrompt, setSchedPrompt] = useState("");
  const [schedTiming, setSchedTiming] = useState<ScheduleTiming>(
    defaultScheduleTiming,
  );

  useEffect(() => {
    if (!open) return;
    setName(role.name);
    setSystemPrompt(role.system_prompt || "");
    setAvatar(role.avatar || "");
    setError(null);
    void listRoleSchedules(role.id)
      .then((r) => setSchedules(r.schedules))
      .catch(() => setSchedules([]));
  }, [open, role]);

  if (!open) return null;

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateRole(role.id, {
        name: name.trim(),
        system_prompt: systemPrompt,
        avatar: avatarStorageRef(avatar),
      });
      onSaved(updated);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (role.is_default) return;
    if (!window.confirm(`删除角色「${role.name}」？其会话将迁回默认角色。`)) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await deleteRole(role.id);
      onDeleted?.();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleAddSchedule() {
    const prompt = schedPrompt.trim();
    if (!prompt) return;
    try {
      const s = await createRoleSchedule(role.id, {
        prompt,
        timing: schedTiming,
        enabled: true,
      });
      setSchedules((prev) => [...prev, s]);
      setSchedPrompt("");
      setSchedTiming(defaultScheduleTiming);
    } catch (e) {
      setError(e instanceof Error ? e.message : "添加定时失败");
    }
  }

  return createPortal(
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal-panel role-settings-modal"
        role="dialog"
        aria-modal="true"
        aria-label="角色设置"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="role-settings-head">
          <h3>角色设置</h3>
          <button type="button" className="role-settings-close" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="role-settings-body">
          {error && <div className="settings-error">{error}</div>}
          <label className="settings-field">
            <span>名称</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={saving}
            />
          </label>
          <label className="settings-field">
            <span>头像（可选）</span>
            <input
              value={avatar}
              onChange={(e) => setAvatar(e.target.value)}
              placeholder="媒体/…png 或 https://…，可留空"
              disabled={saving}
            />
          </label>
          <label className="settings-field">
            <span>系统提示词（人设）</span>
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={6}
              disabled={saving}
              placeholder="该角色的身份与工作方式…"
            />
          </label>

          <div className="role-settings-schedules">
            <h4>定时任务</h4>
            <p className="settings-group-hint">
              按时间表向该角色活跃线发送提示词（后台执行；有进行中回合则顺延）。
            </p>
            <ul className="role-schedule-list">
              {schedules.map((s) => (
                <li key={s.id} className="role-schedule-item">
                  <div className="role-schedule-prompt">{s.prompt}</div>
                  <div className="role-schedule-meta">
                    {s.timing_summary || `每 ${s.interval_hours} 小时`}
                    {s.enabled ? "" : " · 已停用"}
                  </div>
                  <div className="role-schedule-actions">
                    <button
                      type="button"
                      disabled={saving}
                      onClick={() => {
                        void updateRoleSchedule(role.id, s.id, {
                          enabled: !s.enabled,
                        }).then((next) =>
                          setSchedules((prev) =>
                            prev.map((x) => (x.id === next.id ? next : x)),
                          ),
                        );
                      }}
                    >
                      {s.enabled ? "停用" : "启用"}
                    </button>
                    <button
                      type="button"
                      disabled={saving}
                      onClick={() => {
                        void deleteRoleSchedule(role.id, s.id).then(() =>
                          setSchedules((prev) =>
                            prev.filter((x) => x.id !== s.id),
                          ),
                        );
                      }}
                    >
                      删除
                    </button>
                  </div>
                </li>
              ))}
            </ul>
            <div className="role-schedule-add">
              <textarea
                value={schedPrompt}
                onChange={(e) => setSchedPrompt(e.target.value)}
                rows={2}
                placeholder="定时发送的提示词，例如：汇总今日新闻"
                disabled={saving}
              />
              <ScheduleTimingFields
                value={schedTiming}
                onChange={setSchedTiming}
                disabled={saving}
                idPrefix="role-settings-timing"
              />
              <button
                type="button"
                className="sidebar-new-chat"
                onClick={() => void handleAddSchedule()}
                disabled={saving || !schedPrompt.trim()}
              >
                添加定时
              </button>
            </div>
          </div>
        </div>
        <div className="role-settings-foot">
          {!role.is_default && (
            <button
              type="button"
              className="btn-danger"
              onClick={() => void handleDelete()}
              disabled={saving}
            >
              删除角色
            </button>
          )}
          <div className="role-settings-foot-spacer" />
          <button type="button" onClick={onClose} disabled={saving}>
            取消
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={() => void handleSave()}
            disabled={saving || !name.trim()}
          >
            保存
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
