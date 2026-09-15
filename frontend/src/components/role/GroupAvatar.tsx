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
  const tileSize = Math.ceil(size / 2);
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
    face = (
      <div
        className="group-avatar"
        style={{ width: size, height: size }}
        aria-hidden
      >
        {Array.from({ length: 4 }, (_, i) => {
          const member = tiles[i];
          if (!member) {
            return <span key={`empty-${i}`} className="group-avatar-slot" />;
          }
          return (
            <RoleAvatar
              key={member.id}
              name={member.name}
              seed={member.id}
              avatar={member.avatar}
              size={tileSize}
            />
          );
        })}
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
