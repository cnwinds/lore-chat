import { useEffect, useState } from "react";
import { useDisplayImageSrc } from "../../hooks/useDisplayImageSrc";
import { avatarDisplaySrc } from "../../utils/kbImageUrls";
import { roleAccent } from "../../utils/roleAccent";

type Props = {
  name: string;
  seed: string;
  avatar?: string | null;
  size?: number;
  className?: string;
};

/** 解析头像引用并处理 SVG blob / 加载失败。 */
export function useRoleAvatarSrc(avatar?: string | null) {
  const resolved = avatarDisplaySrc(avatar);
  const displaySrc = useDisplayImageSrc(resolved || "");
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setFailed(false);
  }, [resolved]);
  return {
    showImage: Boolean(resolved) && !failed && Boolean(displaySrc),
    src: displaySrc,
    onError: () => setFailed(true),
  };
}

export function RoleAvatar({
  name,
  seed,
  avatar,
  size = 36,
  className = "",
}: Props) {
  const letter = (name.trim()[0] || "?").toUpperCase();
  const { showImage, src, onError } = useRoleAvatarSrc(avatar);
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
        <span className="role-avatar-letter">{letter}</span>
      )}
    </div>
  );
}
