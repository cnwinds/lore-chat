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
import { routineListTitle } from "../../utils/routineTitle";
import { RoutineDetailView } from "./RoutineDetailView";
import type { ScheduleTiming } from "../../utils/scheduleTiming";
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

  const [name, setName] = useState("");
  const [avatar, setAvatar] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [detail, setDetail] = useState<RoleSchedule | "new" | null>(null);
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
      setDetail(null);
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
      setDetail(null);
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

  async function handleSaveRoutine(body: {
    prompt: string;
    timing: ScheduleTiming;
    enabled: boolean;
  }) {
    if (!roleId) return;
    try {
      setSaving(true);
      if (detail && detail !== "new") {
        const next = await updateRoleSchedule(roleId, detail.id, body);
        setSchedules((prev) => prev.map((x) => (x.id === next.id ? next : x)));
        setDetail(next);
      } else {
        const created = await createRoleSchedule(roleId, body);
        setSchedules((prev) => [...prev, created]);
        setDetail(created);
      }
    } catch (err) {
      console.error("Failed to save schedule:", err);
      window.alert(detail === "new" ? "创建例行任务失败" : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteRoutine() {
    if (!roleId || !detail || detail === "new") return;
    if (!window.confirm("确定删除这个例行任务？")) return;
    try {
      setSaving(true);
      await deleteRoleSchedule(roleId, detail.id);
      setSchedules((prev) => prev.filter((x) => x.id !== detail.id));
      setDetail(null);
    } catch (err) {
      console.error("Failed to delete schedule:", err);
      window.alert("删除失败");
    } finally {
      setSaving(false);
    }
  }

  const coverBg = role ? roleAccent(role.id) : "hsl(220 20% 24%)";
  const showingDetail = detail !== null;

  return (
    <aside
      className={`role-config-panel${collapsed ? " role-config-panel--collapsed" : ""}${showingDetail ? " role-config-panel--routine" : ""}`}
      hidden={collapsed}
    >
      <div className="role-config-toolbar">
        {showingDetail ? (
          <button
            type="button"
            className="role-config-icon-btn"
            onClick={() => setDetail(null)}
            title="返回"
            aria-label="返回例行任务列表"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path
                d="M15 6l-6 6 6 6"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        ) : (
          <span className="role-config-toolbar-spacer" />
        )}
        <div className="role-config-toolbar-end">
          {!showingDetail ? (
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
          ) : null}
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
      </div>

      {!roleId ? (
        <div className="role-config-empty">请选择一个角色</div>
      ) : loading && !role ? (
        <div className="role-config-loading">加载中…</div>
      ) : showingDetail && roleId ? (
        <RoutineDetailView
          roleId={roleId}
          schedule={detail && detail !== "new" ? detail : null}
          saving={saving}
          onSave={(body) => void handleSaveRoutine(body)}
          onDelete={
            detail && detail !== "new"
              ? () => void handleDeleteRoutine()
              : undefined
          }
        />
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
                      : { background: coverBg }
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
              <div className="role-config-cover-caption">
                {role?.name}
              </div>
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

          <div
            className={`role-config-routines${schedules.length === 0 ? " role-config-routines--empty" : ""}`}
          >
            {schedules.length > 0 ? (
              <>
                <div className="role-config-routines-head">
                  <h4>例行任务</h4>
                  <button
                    type="button"
                    className="role-config-icon-btn"
                    onClick={() => setDetail("new")}
                    disabled={!roleId}
                    title="创建例行任务"
                    aria-label="创建例行任务"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
                      <path
                        d="M12 5v14M5 12h14"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                      />
                    </svg>
                  </button>
                </div>
                <ul className="role-config-schedules">
                  {schedules.map((schedule) => (
                    <li key={schedule.id}>
                      <button
                        type="button"
                        className={`role-config-schedule-item${schedule.enabled ? "" : " is-off"}`}
                        onClick={() => setDetail(schedule)}
                      >
                        <span
                          className={`role-config-schedule-dot${schedule.enabled ? " is-on" : ""}`}
                          aria-hidden
                        />
                        <span className="role-config-schedule-copy">
                          <span className="role-config-schedule-prompt">
                            {routineListTitle(schedule.prompt)}
                          </span>
                          <span className="role-config-schedule-meta">
                            {schedule.timing_summary ||
                              `每 ${schedule.interval_hours} 小时`}
                            {schedule.enabled ? "" : " · 已停用"}
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <>
                <p className="role-config-routines-hint">
                  例行任务是这个角色按时间表定期运行的任务。
                </p>
                <button
                  type="button"
                  className="role-config-create-routine"
                  onClick={() => setDetail("new")}
                  disabled={!roleId}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
                    <path
                      d="M12 5v14M5 12h14"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                    />
                  </svg>
                  创建例行任务
                </button>
              </>
            )}
          </div>
        </>
      )}
    </aside>
  );
}
