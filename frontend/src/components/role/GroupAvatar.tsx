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

export function GroupAvatar({
  name,
  seed,
  avatar,
  members = [],
  size = 36,
  className = "",
}: Props) {
  if (avatar) {
    return (
      <RoleAvatar
        name={name}
        seed={seed}
        avatar={avatar}
        size={size}
        className={className}
      />
    );
  }
  const tiles = members.slice(0, 4);
  if (tiles.length <= 1) {
    return (
      <RoleAvatar
        name={name}
        seed={seed}
        avatar={tiles[0]?.avatar}
        size={size}
        className={className}
      />
    );
  }
  const count = tiles.length as 2 | 3 | 4;
  return (
    <div
      className={`group-avatar group-avatar--${count}${className ? ` ${className}` : ""}`}
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
