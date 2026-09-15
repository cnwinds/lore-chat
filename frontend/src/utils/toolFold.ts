import type { TimelineBlock } from "../types/chat";

type ToolBlock = Extract<TimelineBlock, { type: "tool" }>;

/** 未作答的征询须展开，方便直接选择。 */
export function isPendingAskTool(block: ToolBlock): boolean {
  return (
    (block.tool === "ask_user" || block.tool === "sandbox_run") &&
    block.status === "done" &&
    !block.choice_resolved &&
    !!block.question_id &&
    Array.isArray(block.options) &&
    block.options.length > 0
  );
}

/**
 * 工具卡默认是否展开。
 * 信息流折叠块一律收起，由用户点开；只有未答征询例外。
 */
export function toolBlockDefaultOpen(block: ToolBlock): boolean {
  return isPendingAskTool(block);
}
