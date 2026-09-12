import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import type { RoleSummary } from "../../api";

type Props = {
  open: boolean;
  roles: RoleSummary[];
  onClose: () => void;
  onConfirm: (title: string, roleIds: string[]) => void;
};

export function CreateGroupModal({ open, roles, onClose, onConfirm }: Props) {
  const [title, setTitle] = useState("");
  const [picked, setPicked] = useState<string[]>([]);

  const selectable = useMemo(
    () => roles.filter((r) => !r.is_default || roles.length <= 8),
    [roles],
  );

  if (!open) return null;

  function toggle(id: string) {
    setPicked((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const name = title.trim() || "群聊";
    if (picked.length < 2) return;
    onConfirm(name, picked);
    setTitle("");
    setPicked([]);
  }

  function handleCancel() {
    onClose();
    setTitle("");
    setPicked([]);
  }

  return createPortal(
    <div className="modal-backdrop" role="presentation" onClick={handleCancel}>
      <form
        className="modal-panel role-settings-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-group-title"
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
      >
        <div className="role-settings-head">
          <h3 id="create-group-title">创建群聊</h3>
          <button
            type="button"
            className="role-settings-close"
            onClick={handleCancel}
            aria-label="关闭"
          >
            ×
          </button>
        </div>
        <div className="role-settings-body">
          <label className="settings-field">
            <span>群名称</span>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="例如：登录页协作"
              autoFocus
            />
          </label>
          <div className="settings-field">
            <span>圈选角色（至少两人）</span>
            <div className="create-group-roles">
              {selectable.map((role) => (
                <label key={role.id} className="create-group-role">
                  <input
                    type="checkbox"
                    checked={picked.includes(role.id)}
                    onChange={() => toggle(role.id)}
                  />
                  {role.name}
                </label>
              ))}
            </div>
          </div>
        </div>
        <div className="role-settings-foot">
          <button type="button" onClick={handleCancel}>
            取消
          </button>
          <button
            type="submit"
            className="btn-primary"
            disabled={picked.length < 2}
          >
            创建
          </button>
        </div>
      </form>
    </div>,
    document.body,
  );
}
