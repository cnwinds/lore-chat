import { useEffect, useState } from "react";
import {
  createRoleSchedule,
  deleteRoleSchedule,
  getRole,
  listRoleSchedules,
  updateRole,
  updateRoleSchedule,
  type Role,
  type RoleSchedule,
} from "../../api";
import { avatarStorageRef } from "../../utils/kbImageUrls";
import { roleAccent } from "../../utils/roleAccent";
import { useRoleAvatarSrc } from "../../hooks/useRoleAvatarSrc";

type Props = {
  roleId: string | null;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  onRoleUpdated?: () => void;
};

export function RoleConfigPanel({
  roleId,
  collapsed = false,
  onToggleCollapsed,
  onRoleUpdated,
}: Props) {
  const [role, setRole] = useState<Role | null>(null);
  const [schedules, setSchedules] = useState<RoleSchedule[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [creating, setCreating] = useState(false);

  const [name, setName] = useState("");
  const [avatar, setAvatar] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [schedPrompt, setSchedPrompt] = useState("");
  const [schedHours, setSchedHours] = useState(24);
  const coverAvatar = useRoleAvatarSrc(role?.avatar);

  async function loadRole(id: string) {
    try {
      setLoading(true);
      const [roleData, schedulesData] = await Promise.all([
        getRole(id),
        listRoleSchedules(id),
      ]);
      setRole(roleData);
      setSchedules(schedulesData.schedules);
      setName(roleData.name);
      setAvatar(roleData.avatar || "");
      setSystemPrompt(roleData.system_prompt || "");
      setEditing(false);
      setCreating(false);
    } catch (err) {
      console.error("Failed to load role:", err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (roleId) {
      void loadRole(roleId);
    } else {
      setRole(null);
      setSchedules([]);
      setName("");
      setAvatar("");
      setSystemPrompt("");
      setEditing(false);
      setCreating(false);
    }
  }, [roleId]);

  async function handleSaveIdentity() {
    if (!roleId || !role) return;
    try {
      setSaving(true);
      const updated = await updateRole(roleId, {
        name: name.trim() || role.name,
        avatar: avatarStorageRef(avatar),
        system_prompt: systemPrompt,
      });
      setRole(updated);
      setEditing(false);
      onRoleUpdated?.();
    } catch (err) {
      console.error("Failed to update role:", err);
      window.alert("保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleAddSchedule() {
    if (!roleId) return;
    const prompt = schedPrompt.trim();
    if (!prompt) return;
    try {
      setSaving(true);
      const created = await createRoleSchedule(roleId, {
        prompt,
        interval_hours: schedHours,
        enabled: true,
      });
      setSchedules((prev) => [...prev, created]);
      setSchedPrompt("");
      setSchedHours(24);
      setCreating(false);
    } catch (err) {
      console.error("Failed to create schedule:", err);
      window.alert("创建例行任务失败");
    } finally {
      setSaving(false);
    }
  }

  const coverBg = role ? roleAccent(role.id) : "hsl(220 20% 24%)";

  return (
    <aside
      className={`role-config-panel${collapsed ? " role-config-panel--collapsed" : ""}`}
      hidden={collapsed}
    >
      <div className="role-config-toolbar">
        <button
          type="button"
          className={`role-config-icon-btn${editing ? " role-config-icon-btn--on" : ""}`}
          onClick={() => setEditing((v) => !v)}
          title="角色设置"
          aria-label="角色设置"
          disabled={!role}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
            <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2" />
            <path
              d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9c.3.7 1 1.2 1.8 1.2H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinejoin="round"
            />
          </svg>
        </button>
        <button
          type="button"
          className="role-config-icon-btn"
          onClick={onToggleCollapsed}
          title="收起角色设置"
          aria-label="收起角色设置"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M9 6l6 6-6 6M14 6l6 6-6 6"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>

      {!roleId ? (
        <div className="role-config-empty">请选择一个角色</div>
      ) : loading && !role ? (
        <div className="role-config-loading">加载中…</div>
      ) : (
        <>
          <div className="role-config-main">
            <button
              type="button"
              className="role-config-cover"
              onClick={() => setEditing(true)}
              title="编辑角色"
            >
              <div
                className="role-config-cover-art"
                style={
                  coverAvatar.showImage
                    ? undefined
                    : {
                        background: `radial-gradient(120% 90% at 28% 8%, color-mix(in srgb, ${coverBg} 42%, white), ${coverBg})`,
                      }
                }
              >
                {coverAvatar.showImage && coverAvatar.src ? (
                  <img
                    src={coverAvatar.src}
                    alt=""
                    onError={coverAvatar.onError}
                  />
                ) : (
                  <span className="role-config-cover-letter">
                    {(role?.name.trim()[0] || "?").toUpperCase()}
                  </span>
                )}
              </div>
              <div className="role-config-cover-caption">{role?.name}</div>
            </button>

            {editing ? (
              <div className="role-config-editor">
                <label className="role-config-label">
                  <span>名称</span>
                  <input
                    type="text"
                    className="role-config-input"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="角色名称"
                  />
                </label>
                <label className="role-config-label">
                  <span>头像</span>
                  <input
                    type="text"
                    className="role-config-input"
                    value={avatar}
                    onChange={(e) => setAvatar(e.target.value)}
                    placeholder="媒体/…png 或 https://…"
                  />
                </label>
                <label className="role-config-label">
                  <span>人设</span>
                  <textarea
                    className="role-config-textarea"
                    value={systemPrompt}
                    onChange={(e) => setSystemPrompt(e.target.value)}
                    placeholder="这个角色是谁、怎么协作…"
                    rows={6}
                  />
                </label>
                <div className="role-config-editor-actions">
                  <button
                    type="button"
                    className="role-config-ghost-btn"
                    onClick={() => {
                      if (role) {
                        setName(role.name);
                        setAvatar(role.avatar || "");
                        setSystemPrompt(role.system_prompt || "");
                      }
                      setEditing(false);
                    }}
                    disabled={saving}
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    className="role-config-primary-btn"
                    onClick={() => void handleSaveIdentity()}
                    disabled={saving}
                  >
                    {saving ? "保存中…" : "保存"}
                  </button>
                </div>
              </div>
            ) : null}
          </div>

          <div className="role-config-routines">
            <p className="role-config-routines-hint">
              例行任务是这个角色按时间表定期运行的任务。
            </p>
            {schedules.length > 0 ? (
              <ul className="role-config-schedules">
                {schedules.map((schedule) => (
                  <li key={schedule.id} className="role-config-schedule-item">
                    <div className="role-config-schedule-prompt">
                      {schedule.prompt}
                    </div>
                    <div className="role-config-schedule-meta">
                      每 {schedule.interval_hours} 小时
                      {schedule.enabled ? "" : " · 已停用"}
                    </div>
                    <div className="role-config-schedule-actions">
                      <button
                        type="button"
                        disabled={saving || !roleId}
                        onClick={() => {
                          if (!roleId) return;
                          void updateRoleSchedule(roleId, schedule.id, {
                            enabled: !schedule.enabled,
                          }).then((next) =>
                            setSchedules((prev) =>
                              prev.map((x) => (x.id === next.id ? next : x)),
                            ),
                          );
                        }}
                      >
                        {schedule.enabled ? "停用" : "启用"}
                      </button>
                      <button
                        type="button"
                        disabled={saving || !roleId}
                        onClick={() => {
                          if (!roleId) return;
                          void deleteRoleSchedule(roleId, schedule.id).then(() =>
                            setSchedules((prev) =>
                              prev.filter((x) => x.id !== schedule.id),
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
            ) : null}
            {creating ? (
              <div className="role-config-schedule-form">
                <textarea
                  className="role-config-textarea"
                  value={schedPrompt}
                  onChange={(e) => setSchedPrompt(e.target.value)}
                  rows={3}
                  placeholder="定时发送的提示词，例如：汇总今日进展"
                  disabled={saving}
                />
                <label className="role-config-label">
                  <span>间隔（小时）</span>
                  <input
                    type="number"
                    className="role-config-input"
                    min={0.5}
                    step={0.5}
                    value={schedHours}
                    onChange={(e) => setSchedHours(Number(e.target.value) || 24)}
                    disabled={saving}
                  />
                </label>
                <div className="role-config-editor-actions">
                  <button
                    type="button"
                    className="role-config-ghost-btn"
                    onClick={() => {
                      setCreating(false);
                      setSchedPrompt("");
                    }}
                    disabled={saving}
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    className="role-config-primary-btn"
                    onClick={() => void handleAddSchedule()}
                    disabled={saving || !schedPrompt.trim()}
                  >
                    创建
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                className="role-config-create-routine"
                onClick={() => setCreating(true)}
                disabled={!roleId}
              >
                创建例行任务
              </button>
            )}
          </div>
        </>
      )}
    </aside>
  );
}
