import { useState } from "react";
import { createPortal } from "react-dom";

type Props = {
  open: boolean;
  onClose: () => void;
  onConfirm: (name: string, avatar: string) => void;
};

export function CreateRoleModal({ open, onClose, onConfirm }: Props) {
  const [name, setName] = useState("");
  const [avatar, setAvatar] = useState("");

  if (!open) return null;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) return;
    onConfirm(trimmedName, avatar.trim());
    setName("");
    setAvatar("");
  }

  function handleCancel() {
    onClose();
    setName("");
    setAvatar("");
  }

  return createPortal(
    <div
      className="modal-backdrop"
      role="presentation"
      onClick={handleCancel}
    >
      <form
        className="modal-panel role-settings-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-role-title"
        onClick={(e) => e.stopPropagation()}
        onSubmit={handleSubmit}
      >
        <div className="role-settings-head">
          <h3 id="create-role-title">创建新角色</h3>
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
            <span>角色名称</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如：股票研究员"
              autoFocus
              required
            />
          </label>
          <label className="settings-field">
            <span>头像（可选）</span>
            <input
              type="text"
              value={avatar}
              onChange={(e) => setAvatar(e.target.value)}
              placeholder="媒体/…png 或 https://…"
            />
          </label>
          <p className="settings-group-hint">
            创建后将进入角色引导，助手会帮你定义职责与人设。
          </p>
        </div>
        <div className="role-settings-foot">
          <div className="role-settings-foot-spacer" />
          <button type="button" onClick={handleCancel}>
            取消
          </button>
          <button
            type="submit"
            className="btn-primary"
            disabled={!name.trim()}
          >
            创建
          </button>
        </div>
      </form>
    </div>,
    document.body,
  );
}
