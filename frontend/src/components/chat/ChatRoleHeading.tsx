import { RoleAvatar } from "../role/RoleAvatar";

type Props = {
  name: string;
  roleId?: string | null;
  avatar?: string | null;
  size?: number;
};

export function ChatRoleHeading({
  name,
  roleId = null,
  avatar = null,
  size = 22,
}: Props) {
  return (
    <span className="chat-role-heading">
      <RoleAvatar
        name={name}
        seed={roleId || name}
        avatar={avatar}
        size={size}
      />
      <span className="chat-role-heading-name">{name}</span>
    </span>
  );
}
