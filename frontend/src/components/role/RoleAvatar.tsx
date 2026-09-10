import { roleAccent } from "../../utils/roleAccent";

type Props = {
  name: string;
  seed: string;
  avatar?: string | null;
  size?: number;
  className?: string;
};

export function RoleAvatar({
  name,
  seed,
  avatar,
  size = 36,
  className = "",
}: Props) {
  const letter = (name.trim()[0] || "?").toUpperCase();
  return (
    <div
      className={`role-avatar${className ? ` ${className}` : ""}`}
      style={{
        width: size,
        height: size,
        background: avatar ? undefined : roleAccent(seed),
      }}
      aria-hidden
    >
      {avatar ? (
        <img src={avatar} alt="" />
      ) : (
        <span className="role-avatar-letter">{letter}</span>
      )}
    </div>
  );
}
