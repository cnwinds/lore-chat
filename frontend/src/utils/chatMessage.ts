import type { ChatMessage, SourceRef, TimelineBlock } from "../api";

export function kbPathFromToolResult(
  data: Record<string, unknown>,
): string | undefined {
  const sources = data.sources as SourceRef[] | undefined;
  const kb = sources?.find((s) => s.type === "kb");
  return kb?.path;
}

export function formatMessageTs(ts: string): string {
  try {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return "";
  }
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
