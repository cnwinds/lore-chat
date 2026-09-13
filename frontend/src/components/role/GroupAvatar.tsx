import { RoleAvatar } from "./RoleAvatar";
import type { RoomParticipant } from "../../types/chat";

type Props = {
  name: string;
  seed: string;
  avatar?: string | null;
  members?: RoomParticipant[];
  size?: number;
  className?: string;
};

function GroupMark({ size }: { size: number }) {
  const mark = Math.max(12, Math.min(18, Math.round(size * 0.42)));
  return (
    <span
      className="group-avatar-mark"
      style={{ width: mark, height: mark }}
      title="群聊"
    >
      <svg
        width={Math.max(8, mark - 4)}
        height={Math.max(8, mark - 4)}
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden
      >
        <circle cx="9" cy="8.2" r="3" stroke="currentColor" strokeWidth="2" />
        <circle cx="16.2" cy="9" r="2.4" stroke="currentColor" strokeWidth="2" />
        <path
          d="M3.6 18.2c.6-2.6 2.7-4 5.4-4s4.8 1.4 5.4 4"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <path
          d="M13.8 17.6c.4-1.4 1.6-2.2 3.2-2.2 1.7 0 2.9.9 3.3 2.4"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}

export function GroupAvatar({
  name,
  seed,
  avatar,
  members = [],
  size = 36,
  className = "",
}: Props) {
  const tiles = members.slice(0, 4);
  let face;
  if (avatar) {
    face = (
      <RoleAvatar name={name} seed={seed} avatar={avatar} size={size} />
    );
  } else if (tiles.length <= 1) {
    face = (
      <RoleAvatar
        name={name}
        seed={seed}
        avatar={tiles[0]?.avatar}
        size={size}
      />
    );
  } else {
    const count = tiles.length as 2 | 3 | 4;
    face = (
      <div
        className={`group-avatar group-avatar--${count}`}
        style={{ width: size, height: size }}
        aria-hidden
      >
        {tiles.map((m) => (
          <RoleAvatar
            key={m.id}
            name={m.name}
            seed={m.id}
            avatar={m.avatar}
            size={Math.ceil(size / 2)}
          />
        ))}
      </div>
    );
  }
  return (
    <div
      className={`group-avatar-host${className ? ` ${className}` : ""}`}
      style={{ width: size, height: size }}
      aria-hidden
    >
      {face}
      <GroupMark size={size} />
    </div>
  );
}
