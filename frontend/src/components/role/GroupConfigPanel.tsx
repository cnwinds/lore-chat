import { useEffect, useMemo, useState } from "react";
import {
  getRoom,
  updateRoom,
  type RoleSummary,
  type RoomParticipant,
} from "../../api";
import type { RoomSummary } from "../../types/chat";
import { avatarStorageRef } from "../../utils/kbImageUrls";
import { GroupAvatar } from "./GroupAvatar";
import { RoleAvatar } from "./RoleAvatar";
import { RoleMemberPicker } from "./RoleMemberPicker";

export type GroupConfigSeed = {
  title?: string | null;
  avatar?: string | null;
  participants?: RoomParticipant[];
  participant_role_ids?: string[];
};

type Props = {
  roomId: string | null;
  roles: RoleSummary[];
  seed?: GroupConfigSeed | null;
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  editRequestKey?: number;
  onSaved?: (room: RoomSummary) => void;
  onDeleted?: (id: string) => Promise<void> | void;
};

export function GroupConfigPanel({
  roomId,
  roles,
  seed = null,
  collapsed = false,
  onToggleCollapsed,
  editRequestKey = 0,
  onSaved,
  onDeleted,
}: Props) {
  const [room, setRoom] = useState<RoomSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState("");
  const [avatar, setAvatar] = useState("");
  const [picked, setPicked] = useState<string[]>([]);

  async function loadRoom(id: string, keepEditing: boolean) {
    try {
      setLoading(true);
      const data = await getRoom(id);
      setRoom(data);
      setTitle(data.title || "");
      setAvatar(data.avatar || "");
      setPicked(data.participant_role_ids || []);
      if (!keepEditing) setEditing(false);
    } catch (err) {
      console.error("Failed to load group:", err);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (roomId) {
      void loadRoom(roomId, false);
    } else {
      setRoom(null);
      setTitle("");
      setAvatar("");
      setPicked([]);
      setEditing(false);
    }
  }, [roomId]);

  useEffect(() => {
    if (editRequestKey > 0) setEditing(true);
  }, [editRequestKey]);

  const displayTitle = room?.title || seed?.title || "群聊";
  const displayAvatar = room?.avatar ?? seed?.avatar ?? null;
  const members = useMemo(() => {
    const fromRoom = room?.participants?.length
      ? room.participants
      : seed?.participants || [];
    if (fromRoom.length) return fromRoom;
    const ids = room?.participant_role_ids || seed?.participant_role_ids || [];
    return roles
      .filter((role) => ids.includes(role.id))
      .map((role) => ({
        id: role.id,
        name: role.name,
        avatar: role.avatar,
      }));
  }, [room, seed, roles]);

  function toggleMember(id: string) {
    setPicked((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  function revertEditor() {
    const source = room;
    setTitle(source?.title || seed?.title || "");
    setAvatar(source?.avatar || seed?.avatar || "");
    setPicked(source?.participant_role_ids || seed?.participant_role_ids || []);
    setEditing(false);
  }

  async function handleSave() {
    if (!roomId) return;
    if (picked.length < 2) return;
    try {
      setSaving(true);
      const updated = await updateRoom(roomId, {
        title: title.trim() || "群聊",
        avatar: avatarStorageRef(avatar),
        role_ids: picked,
      });
      setRoom(updated);
      setTitle(updated.title || "");
      setAvatar(updated.avatar || "");
      setPicked(updated.participant_role_ids || []);
      setEditing(false);
      onSaved?.(updated);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!roomId) return;
    if (!window.confirm(`确定删除群「${displayTitle}」？此操作不可撤销。`)) {
      return;
    }
    try {
      setSaving(true);
      await onDeleted?.(roomId);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "删除失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <aside
      className={`role-config-panel${collapsed ? " role-config-panel--collapsed" : ""}`}
      hidden={collapsed}
      aria-label="群设置"
    >
      <div className="role-config-toolbar">
        <span className="role-config-toolbar-spacer" />
        <div className="role-config-toolbar-end">
          <button
            type="button"
            className={`role-config-icon-btn${editing ? " role-config-icon-btn--on" : ""}`}
            onClick={() => setEditing((v) => !v)}
            title="群设置"
            aria-label="群设置"
            disabled={!roomId}
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
            title="收起群设置"
            aria-label="收起群设置"
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

      {!roomId ? (
        <div className="role-config-empty">请选择一个群</div>
      ) : loading && !room && !seed ? (
        <div className="role-config-loading">加载中…</div>
      ) : (
        <>
          <div className="role-config-main">
            <button
              type="button"
              className="role-config-cover"
              onClick={() => setEditing(true)}
              title="编辑群"
            >
              <div className="role-config-cover-art role-config-cover-art--group">
                <GroupAvatar
                  name={displayTitle}
                  seed={roomId || displayTitle}
                  avatar={displayAvatar}
                  members={members}
                  size={160}
                />
              </div>
              <div className="role-config-cover-caption">{displayTitle}</div>
            </button>

            {editing ? (
              <div className="role-config-editor">
                <label className="role-config-label">
                  <span>群名称</span>
                  <input
                    type="text"
                    className="role-config-input"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="群名称"
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
                <div className="role-config-label">
                  <span>成员（至少两人）</span>
                  <RoleMemberPicker
                    roles={roles}
                    picked={picked}
                    onToggle={toggleMember}
                  />
                </div>
                <div className="role-config-editor-actions">
                  <button
                    type="button"
                    className="role-config-ghost-btn"
                    onClick={revertEditor}
                    disabled={saving}
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    className="role-config-primary-btn"
                    onClick={() => void handleSave()}
                    disabled={saving || picked.length < 2}
                  >
                    {saving ? "保存中…" : "保存"}
                  </button>
                </div>
                <button
                  type="button"
                  className="role-config-danger-btn"
                  onClick={() => void handleDelete()}
                  disabled={saving}
                >
                  删除群聊
                </button>
              </div>
            ) : null}
          </div>

          {!editing ? (
            <div
              className={`role-config-members${members.length === 0 ? " role-config-routines--empty" : ""}`}
            >
              {members.length > 0 ? (
                <>
                  <div className="role-config-routines-head">
                    <h4>成员</h4>
                  </div>
                  <ul className="role-config-member-list">
                    {members.map((member) => (
                      <li key={member.id} className="role-config-member-item">
                        <RoleAvatar
                          name={member.name}
                          seed={member.id}
                          avatar={member.avatar}
                          size={28}
                        />
                        <span>{member.name}</span>
                      </li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="role-config-routines-hint">
                  这个群还没有成员。点按齿轮把角色圈进来。
                </p>
              )}
            </div>
          ) : null}
        </>
      )}
    </aside>
  );
}
