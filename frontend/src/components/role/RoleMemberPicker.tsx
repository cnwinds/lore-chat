import { useMemo, useState } from "react";
import type { RoleSummary } from "../../api";
import { RoleAvatar } from "./RoleAvatar";

type Props = {
  roles: RoleSummary[];
  picked: string[];
  onToggle: (id: string) => void;
  filterable?: boolean;
};

export function RoleMemberPicker({
  roles,
  picked,
  onToggle,
  filterable = true,
}: Props) {
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();
  const visible = useMemo(() => {
    if (!q) return roles;
    return roles.filter((role) => role.name.toLowerCase().includes(q));
  }, [roles, q]);

  const selected = roles.filter((role) => picked.includes(role.id));

  return (
    <div className="role-member-picker">
      {selected.length > 0 ? (
        <div className="role-member-picked" aria-label="已选成员">
          {selected.map((role) => (
            <button
              key={role.id}
              type="button"
              className="role-member-chip"
              onClick={() => onToggle(role.id)}
              title={`移除 ${role.name}`}
            >
              <RoleAvatar
                name={role.name}
                seed={role.id}
                avatar={role.avatar}
                size={22}
              />
              <span>{role.name}</span>
              <span aria-hidden>×</span>
            </button>
          ))}
        </div>
      ) : null}
      {filterable ? (
        <input
          type="search"
          className="role-member-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索角色"
          aria-label="搜索角色"
        />
      ) : null}
      <div className="role-member-list" role="listbox" aria-multiselectable>
        {visible.length === 0 ? (
          <div className="role-member-empty">没有匹配的角色</div>
        ) : (
          visible.map((role) => {
            const on = picked.includes(role.id);
            return (
              <button
                key={role.id}
                type="button"
                role="option"
                aria-selected={on}
                className={`role-member-row${on ? " is-picked" : ""}`}
                onClick={() => onToggle(role.id)}
              >
                <RoleAvatar
                  name={role.name}
                  seed={role.id}
                  avatar={role.avatar}
                  size={32}
                />
                <span className="role-member-row-name">{role.name}</span>
                <span
                  className={`role-member-check${on ? " is-on" : ""}`}
                  aria-hidden
                >
                  {on ? "✓" : ""}
                </span>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
