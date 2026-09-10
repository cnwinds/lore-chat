import { useEffect, useState } from "react";
import {
  getRole,
  updateRole,
  listRoleSchedules,
  type Role,
  type RoleSchedule,
} from "../../api";

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

  // Form state
  const [name, setName] = useState("");
  const [avatar, setAvatar] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");

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
    }
  }, [roleId]);

  async function handleSave() {
    if (!roleId || !role) return;

    try {
      setSaving(true);
      const updated = await updateRole(roleId, {
        name: name.trim() || role.name,
        avatar: avatar.trim() || null,
        system_prompt: systemPrompt,
      });
      setRole(updated);
      onRoleUpdated?.();
    } catch (err) {
      console.error("Failed to update role:", err);
      alert("保存失败");
    } finally {
      setSaving(false);
    }
  }

  if (collapsed) {
    return (
      <aside className="role-config-panel role-config-panel--collapsed">
        <button
          type="button"
          className="role-config-toggle role-config-toggle--collapsed"
          onClick={onToggleCollapsed}
          title="展开配置面板"
        >
          ‹
        </button>
      </aside>
    );
  }

  return (
    <aside className="role-config-panel">
      <div className="role-config-head">
        <h3 className="role-config-title">角色配置</h3>
        <button
          type="button"
          className="role-config-toggle"
          onClick={onToggleCollapsed}
          title="收起配置面板"
        >
          ›
        </button>
      </div>

      {!roleId ? (
        <div className="role-config-empty">请选择一个角色</div>
      ) : loading ? (
        <div className="role-config-loading">加载中...</div>
      ) : (
        <div className="role-config-body">
          <div className="role-config-section">
            <label className="role-config-label">
              <span>名称</span>
              <input
                type="text"
                className="role-config-input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="输入角色名称"
              />
            </label>
          </div>

          <div className="role-config-section">
            <label className="role-config-label">
              <span>头像 URL</span>
              <input
                type="text"
                className="role-config-input"
                value={avatar}
                onChange={(e) => setAvatar(e.target.value)}
                placeholder="https://..."
              />
            </label>
          </div>

          <div className="role-config-section">
            <label className="role-config-label">
              <span>人设（System Prompt）</span>
              <textarea
                className="role-config-textarea"
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                placeholder="输入角色人设..."
                rows={8}
              />
            </label>
          </div>

          <div className="role-config-section">
            <div className="role-config-section-head">
              <span className="role-config-label-text">定时任务</span>
              <button
                type="button"
                className="role-config-add-schedule"
                title="添加定时任务"
                disabled
              >
                ＋
              </button>
            </div>
            {schedules.length === 0 ? (
              <div className="role-config-schedules-empty">暂无定时任务</div>
            ) : (
              <div className="role-config-schedules">
                {schedules.map((schedule) => (
                  <div key={schedule.id} className="role-config-schedule-item">
                    <div className="role-config-schedule-cron">
                      每 {schedule.interval_hours} 小时
                    </div>
                    <div className="role-config-schedule-prompt">
                      {schedule.prompt}
                    </div>
                    <div className="role-config-schedule-status">
                      {schedule.enabled ? "已启用" : "已禁用"}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="role-config-actions">
            <button
              type="button"
              className="role-config-save-btn"
              onClick={handleSave}
              disabled={saving || !roleId}
            >
              {saving ? "保存中..." : "保存"}
            </button>
          </div>
        </div>
      )}
    </aside>
  );
}
