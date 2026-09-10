import { useEffect, useState } from "react";
import { listRoles, type Role } from "../../api";
import { formatSidebarConversationTime } from "../../utils/displayTime";

type Props = {
  activeRoleId: string | null;
  onSelectRole: (roleId: string) => void;
  onNewRole: () => void;
  refreshKey?: number;
};

export function RoleList({
  activeRoleId,
  onSelectRole,
  onNewRole,
  refreshKey = 0,
}: Props) {
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);

  async function loadRoles() {
    try {
      setLoading(true);
      const { roles: data } = await listRoles();
      setRoles(data);
    } catch (err) {
      console.error("Failed to load roles:", err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadRoles();
  }, [refreshKey]);

  return (
    <aside className="role-list">
      <div className="role-list-head">
        <div className="role-list-search">
          <input
            type="text"
            className="role-list-search-input"
            placeholder="搜索..."
            disabled
          />
        </div>
        <button
          type="button"
          className="role-list-new-btn"
          onClick={onNewRole}
          title="新建角色"
        >
          ＋
        </button>
      </div>

      <div className="role-list-scroll">
        {loading && roles.length === 0 ? (
          <div className="role-list-loading">加载中...</div>
        ) : roles.length === 0 ? (
          <div className="role-list-empty">暂无角色</div>
        ) : (
          roles.map((role) => {
            const isActive = activeRoleId === role.id;
            return (
              <button
                key={role.id}
                type="button"
                className={`role-item${isActive ? " role-item--active" : ""}`}
                onClick={() => onSelectRole(role.id)}
              >
                <div className="role-item-avatar">
                  {role.avatar ? (
                    <img src={role.avatar} alt={role.name} />
                  ) : (
                    <span className="role-item-avatar-fallback">
                      {role.name.charAt(0).toUpperCase()}
                    </span>
                  )}
                </div>
                <div className="role-item-content">
                  <div className="role-item-name">{role.name}</div>
                  <div className="role-item-preview">
                    {role.system_prompt
                      ? role.system_prompt.slice(0, 50) + (role.system_prompt.length > 50 ? "..." : "")
                      : "暂无人设"}
                  </div>
                </div>
                <div className="role-item-meta">
                  {formatSidebarConversationTime(role.updated_at)}
                </div>
              </button>
            );
          })
        )}
      </div>
    </aside>
  );
}
