import { roleAccent } from "../../utils/roleAccent";
import { useRoleAvatarSrc } from "../../hooks/useRoleAvatarSrc";

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
  const { showImage, src, onError } = useRoleAvatarSrc(avatar);
  const letterSize = Math.max(8, Math.round(size * 0.42));
  return (
    <div
      className={`role-avatar${className ? ` ${className}` : ""}`}
      style={{
        width: size,
        height: size,
        background: showImage ? undefined : roleAccent(seed),
      }}
      aria-hidden
    >
      {showImage && src ? (
        <img src={src} alt="" onError={onError} />
      ) : (
        <span className="role-avatar-letter" style={{ fontSize: letterSize }}>
          {letter}
        </span>
      )}
    </div>
  );
}
