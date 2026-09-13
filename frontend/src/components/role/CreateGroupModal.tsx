import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import type { RoleSummary } from "../../api";
import { defaultGroupTitle } from "../../utils/groupChatDisplay";
import { RoleMemberPicker } from "./RoleMemberPicker";

type Props = {
  open: boolean;
  roles: RoleSummary[];
  onClose: () => void;
  onConfirm: (title: string, roleIds: string[], avatar: string) => void;
};

export function CreateGroupModal({ open, roles, onClose, onConfirm }: Props) {
  const [title, setTitle] = useState("");
  const [picked, setPicked] = useState<string[]>([]);

  const placeholder = useMemo(
    () => defaultGroupTitle(roles, picked),
    [roles, picked],
  );

  if (!open) return null;

  function toggle(id: string) {
    setPicked((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  function reset() {
    setTitle("");
    setPicked([]);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (picked.length < 2) return;
    onConfirm(title.trim() || placeholder, picked, "");
    reset();
  }

  function handleCancel() {
    onClose();
    reset();
  }

  return createPortal(
    <div className="modal-backdrop" role="presentation" onClick={handleCancel}>
      <form
        className="modal-panel role-settings-modal create-group-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-group-title"
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
      >
        <div className="role-settings-head">
          <h3 id="create-group-title">发起群聊</h3>
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
          {roles.length < 2 ? (
            <p className="settings-group-hint">
              至少需要两个角色才能建群。先创建一个新角色，再把它和现有角色圈在一起。
            </p>
          ) : (
            <>
              <label className="settings-field">
                <span>群名称</span>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={placeholder}
                  autoFocus
                />
              </label>
              <div className="settings-field">
                <span>选择成员（至少两人）</span>
                <RoleMemberPicker
                  roles={roles}
                  picked={picked}
                  onToggle={toggle}
                />
              </div>
            </>
          )}
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
            发起群聊
          </button>
        </div>
      </form>
    </div>,
    document.body,
  );
}
