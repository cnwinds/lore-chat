import { useEffect, useState } from "react";
import { useDisplayImageSrc } from "./useDisplayImageSrc";
import { avatarDisplaySrc } from "../utils/kbImageUrls";

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
