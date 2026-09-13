import {
  useEffect,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { createPortal } from "react-dom";
import { listRooms, type RoomSummary } from "../../api";
import { GroupAvatar } from "./GroupAvatar";

type GroupMenu = {
  room: RoomSummary;
  x: number;
  y: number;
};

type Props = {
  activeGroupId: string | null;
  onSelectGroup: (id: string, room?: RoomSummary) => void;
  onNewGroup: () => void;
  onEditGroup?: (room: RoomSummary) => void;
  onDeleteGroup?: (room: RoomSummary) => void | Promise<void>;
  refreshKey?: number;
  visible?: boolean;
};

export function GroupList({
  activeGroupId,
  onSelectGroup,
  onNewGroup,
  onEditGroup,
  onDeleteGroup,
  refreshKey = 0,
  visible = true,
}: Props) {
  const [rooms, setRooms] = useState<RoomSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [menu, setMenu] = useState<GroupMenu | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

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

  useEffect(() => {
    if (!menu) return;
    function close() {
      setMenu(null);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    function onPointerDown(e: globalThis.MouseEvent) {
      if (menuRef.current?.contains(e.target as Node)) return;
      close();
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onPointerDown);
    window.addEventListener("scroll", close, true);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("scroll", close, true);
    };
  }, [menu]);

  function openMenu(e: ReactMouseEvent<HTMLButtonElement>, room: RoomSummary) {
    e.preventDefault();
    e.stopPropagation();
    const pad = 8;
    const approxW = 140;
    const approxH = 80;
    const x = Math.min(e.clientX, window.innerWidth - approxW - pad);
    const y = Math.min(e.clientY, window.innerHeight - approxH - pad);
    setMenu({ room, x: Math.max(pad, x), y: Math.max(pad, y) });
  }

  async function confirmDelete(room: RoomSummary) {
    setMenu(null);
    if (
      !window.confirm(
        `确定删除群「${room.title || "群聊"}」？此操作不可撤销。`,
      )
    ) {
      return;
    }
    await onDeleteGroup?.(room);
  }

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
                onClick={() => onSelectGroup(room.id, room)}
                onContextMenu={(e) => openMenu(e, room)}
              >
                <div className="role-item-avatar-wrap">
                  <GroupAvatar
                    name={room.title || "群聊"}
                    seed={room.id}
                    avatar={room.avatar}
                    members={room.participants}
                    size={36}
                  />
                </div>
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
      {menu &&
        createPortal(
          <div
            ref={menuRef}
            className="kb-tree-context-menu role-list-context-menu"
            style={{ left: menu.x, top: menu.y }}
            role="menu"
          >
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                const room = menu.room;
                setMenu(null);
                onEditGroup?.(room);
              }}
            >
              群设置
            </button>
            <button
              type="button"
              role="menuitem"
              className="role-list-context-menu--danger"
              onClick={() => void confirmDelete(menu.room)}
            >
              删除群聊
            </button>
          </div>,
          document.body,
        )}
    </section>
  );
}
