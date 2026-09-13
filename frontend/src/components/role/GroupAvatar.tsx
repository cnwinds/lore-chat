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
  const font = Math.max(8, Math.min(11, Math.round(size * 0.28)));
  return (
    <span
      className="group-avatar-mark"
      style={{ fontSize: font }}
      title="群聊"
    >
      群
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
