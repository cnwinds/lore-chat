import type { ChatMessage, SourceRef, TimelineBlock } from "../api";
import { formatMessageTime } from "./displayTime";

export function kbPathFromToolResult(
  data: Record<string, unknown>,
): string | undefined {
  const sources = data.sources as SourceRef[] | undefined;
  const kb = sources?.find((s) => s.type === "kb");
  return kb?.path;
}

/** @deprecated 使用 formatMessageTime；保留别名避免大范围重命名 */
export function formatMessageTs(ts: string): string {
  return formatMessageTime(ts);
}

export function markToolBlockResolved(
  messages: ChatMessage[],
  blockId: string,
  choiceLabel: string,
): ChatMessage[] {
  function patchBlock(block: TimelineBlock): TimelineBlock {
    if (block.type === "tool" && block.id === blockId) {
      return { ...block, choice_resolved: choiceLabel };
    }
    if (block.type === "parallel") {
      return {
        ...block,
        children: block.children.map(patchBlock),
      };
    }
    return block;
  }
  return messages.map((msg) =>
    msg.timeline
      ? { ...msg, timeline: msg.timeline.map(patchBlock) }
      : msg,
  );
}
