import { useEffect, useState } from "react";
import { listRooms, type RoomSummary } from "../../api";

type Props = {
  activeGroupId: string | null;
  onSelectGroup: (id: string) => void;
  onNewGroup: () => void;
  refreshKey?: number;
  visible?: boolean;
};

export function GroupList({
  activeGroupId,
  onSelectGroup,
  onNewGroup,
  refreshKey = 0,
  visible = true,
}: Props) {
  const [rooms, setRooms] = useState<RoomSummary[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    setLoading(true);
    void listRooms("group")
      .then(({ rooms: next }) => {
        if (!cancelled) setRooms(next);
      })
      .catch(() => {
        if (!cancelled) setRooms([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey, visible]);

  if (!visible && rooms.length === 0) return null;

  return (
    <section className="group-list" aria-label="群聊">
      <div className="group-list-head">
        <h4>群聊</h4>
        <button
          type="button"
          className="role-list-new-btn"
          onClick={onNewGroup}
          title="新建群聊"
          aria-label="新建群聊"
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
      <div className="group-list-scroll">
        {loading && rooms.length === 0 ? (
          <div className="role-list-empty">加载中...</div>
        ) : rooms.length === 0 ? (
          <div className="role-list-empty">还没有群。圈几个角色即可开聊。</div>
        ) : (
          rooms.map((room) => {
            const active = activeGroupId === room.id;
            const names = (room.participant_names || []).join("、") || "群聊";
            return (
              <button
                key={room.id}
                type="button"
                className={`role-item${active ? " role-item--active" : ""}`}
                onClick={() => onSelectGroup(room.id)}
              >
                <div className="role-item-content">
                  <div className="role-item-top">
                    <div className="role-item-name">{room.title || "群聊"}</div>
                  </div>
                  <div className="role-item-preview">{names}</div>
                </div>
              </button>
            );
          })
        )}
      </div>
    </section>
  );
}
