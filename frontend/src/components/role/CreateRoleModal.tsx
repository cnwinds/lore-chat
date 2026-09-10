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
      onClick={(e) => e.target === e.currentTarget && handleCancel()}
    >
      <div className="modal-card" style={{ maxWidth: 480 }}>
        <form onSubmit={handleSubmit}>
          <div className="modal-header">
            <h3>创建新角色</h3>
            <button type="button" className="close-btn" onClick={handleCancel}>
              ×
            </button>
          </div>
          <div className="modal-body">
            <div style={{ marginBottom: 16 }}>
              <label
                style={{
                  display: "block",
                  marginBottom: 4,
                  fontSize: 14,
                  fontWeight: 500,
                }}
              >
                角色名称 <span style={{ color: "#f56565" }}>*</span>
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="例如：股票研究员"
                autoFocus
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  fontSize: 14,
                  border: "1px solid var(--border-color, #e2e8f0)",
                  borderRadius: 6,
                  outline: "none",
                }}
              />
            </div>
            <div>
              <label
                style={{
                  display: "block",
                  marginBottom: 4,
                  fontSize: 14,
                  fontWeight: 500,
                }}
              >
                头像 URL（可选）
              </label>
              <input
                type="text"
                value={avatar}
                onChange={(e) => setAvatar(e.target.value)}
                placeholder="https://..."
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  fontSize: 14,
                  border: "1px solid var(--border-color, #e2e8f0)",
                  borderRadius: 6,
                  outline: "none",
                }}
              />
            </div>
            <div
              style={{
                marginTop: 12,
                padding: "8px 12px",
                fontSize: 13,
                color: "#718096",
                backgroundColor: "#f7fafc",
                borderRadius: 6,
              }}
            >
              创建后将进入角色引导流程，助手会帮助你定义职责与人设。
            </div>
          </div>
          <div className="modal-footer">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleCancel}
            >
              取消
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={!name.trim()}
            >
              创建
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body,
  );
}
