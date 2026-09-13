import type { TimelineBlock } from "../types/chat";
import { isLikelyImagePath } from "./kbImageUrls";

type ToolBlock = Extract<TimelineBlock, { type: "tool" }>;

const COLLAPSED_WHILE_LIVE = new Set(["search_kb", "web_search", "fetch_url"]);

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

/** 生图 / write_kb_file SVG / 从沙箱发布的图片等，完成后仍展开以便预览。 */
export function hasPreviewableImageAttachments(block: ToolBlock): boolean {
  return (
    Array.isArray(block.attachments) &&
    block.attachments.some((p) => isLikelyImagePath(p))
  );
}

/**
 * 工具卡默认是否展开。
 * 已结束会话：全部折叠，仅待回答征询与生成的图片/SVG 展开。
 * 流式中：检索/打开链接仍折叠，其余（含沙箱终端）展开。
 */
export function toolBlockDefaultOpen(
  block: ToolBlock,
  opts: { isLive: boolean },
): boolean {
  if (isPendingAskTool(block) || hasPreviewableImageAttachments(block)) {
    return true;
  }
  if (block.tool === "send_message") {
    return true;
  }
  if (!opts.isLive) {
    return false;
  }
  return !COLLAPSED_WHILE_LIVE.has(block.tool);
}
