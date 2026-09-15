import { MediaGalleryPanel } from "../media/MediaGalleryPanel";
import type { DocWidth } from "../../types/doc";
import { KbFloatLayer } from "./KbFloatLayer";

type Props = {
  directory: string;
  refreshKey?: number;
  paths?: string[] | null;
  docWidth?: DocWidth;
  onClose: () => void;
  onToggleWidth?: () => void;
};

/** 媒体图库浮窗：贴在聊天区左缘，与文档浮窗同槽。 */
export function MediaGalleryFloatLayer({
  directory,
  refreshKey = 0,
  paths = null,
  docWidth = "wide",
  onClose,
  onToggleWidth,
}: Props) {
  return (
    <KbFloatLayer onClose={onClose}>
      <MediaGalleryPanel
        directory={directory}
        refreshKey={refreshKey}
        paths={paths}
        docWidth={docWidth}
        onClose={onClose}
        onToggleWidth={onToggleWidth}
      />
    </KbFloatLayer>
  );
}
