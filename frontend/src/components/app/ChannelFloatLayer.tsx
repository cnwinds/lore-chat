import { ChannelPanel } from "../channels/ChannelPanel";
import type { DocWidth } from "../../types/doc";
import { KbFloatLayer } from "./KbFloatLayer";

type Props = {
  docWidth?: DocWidth;
  onClose: () => void;
};

/** 聊天通道浮窗：与媒体图库同一套左缘浮窗壳。 */
export function ChannelFloatLayer({
  docWidth = "wide",
  onClose,
}: Props) {
  return (
    <KbFloatLayer onClose={onClose}>
      <ChannelPanel docWidth={docWidth} onClose={onClose} />
    </KbFloatLayer>
  );
}
