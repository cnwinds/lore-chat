import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import type { RoleSummary } from "../../api";
import type { RoomSummary } from "../../types/chat";
import { avatarStorageRef } from "../../utils/kbImageUrls";

type Props = {
  open: boolean;
  room: RoomSummary | null;
  roles: RoleSummary[];
  onClose: () => void;
  onSave: (patch: {
    title: string;
    avatar: string | null;
    role_ids: string[];
  }) => Promise<void> | void;
  onDelete: () => Promise<void> | void;
};

export function GroupSettingsModal({
  open,
  room,
  roles,
  onClose,
  onSave,
  onDelete,
}: Props) {
  const [title, setTitle] = useState("");
  const [avatar, setAvatar] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const selectable = useMemo(
    () => roles.filter((r) => !r.is_default || roles.length <= 8),
    [roles],
  );

  useEffect(() => {
    if (!open || !room) return;
    setTitle(room.title || "");
    setAvatar(room.avatar || "");
    setPicked(room.participant_role_ids || []);
  }, [open, room]);

  if (!open || !room) return null;
  const editing = room;

  function toggle(id: string) {
    setPicked((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (picked.length < 2) return;
    setSaving(true);
    try {
      await onSave({
        title: title.trim() || "群聊",
        avatar: avatarStorageRef(avatar),
        role_ids: picked,
      });
      onClose();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm(`确定删除群「${editing.title || "群聊"}」？此操作不可撤销。`)) {
      return;
    }
    setSaving(true);
    try {
      await onDelete();
      onClose();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "删除失败");
    } finally {
      setSaving(false);
    }
  }

  return createPortal(
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <form
        className="modal-panel role-settings-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="group-settings-title"
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => void handleSubmit(e)}
      >
        <div className="role-settings-head">
          <h3 id="group-settings-title">群设置</h3>
          <button
            type="button"
            className="role-settings-close"
            onClick={onClose}
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
          <div className="settings-field">
            <span>成员（至少两人）</span>
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
          <button
            type="button"
            className="role-list-context-menu--danger"
            onClick={() => void handleDelete()}
            disabled={saving}
          >
            删除
          </button>
          <button type="button" onClick={onClose}>
            取消
          </button>
          <button
            type="submit"
            className="btn-primary"
            disabled={saving || picked.length < 2}
          >
            保存
          </button>
        </div>
      </form>
    </div>,
    document.body,
  );
}
