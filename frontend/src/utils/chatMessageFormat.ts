/** 聊天消息展示与来源格式化（纯函数，无 HTTP）。 */

import type {
  ChatMessage,
  CumulativeInfo,
  DocContextItem,
  SourceRef,
  TimelineBlock,
} from "../types/chat";

export function normalizeDocContext(
  raw: DocContextItem[] | string[] | undefined,
): DocContextItem[] {
  if (!raw?.length) return [];
  return raw.map((item) => {
    if (typeof item === "string") {
      return { path: item, kind: "document" as const };
    }
    return { path: item.path, kind: "document" as const };
  });
}
/** 提取消息可复制文本；助手仅含 timeline 中的结论文字 */
export function getMessageCopyText(m: ChatMessage): string | null {
  if (m.role === "user") {
    const text = m.text?.trim();
    return text || null;
  }
  if (m.timeline?.length) {
    const parts = m.timeline
      .filter((b): b is Extract<TimelineBlock, { type: "text" }> => b.type === "text")
      .map((b) => b.content.trim())
      .filter(Boolean);
    if (parts.length) return parts.join("\n\n");
  }
  const text = m.text?.trim();
  return text || null;
}
/** 将毫秒格式化为可读耗时 */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  return `${m}m ${rem}s`;
}
/** 按时间线顺序计算各步骤完成时的累计耗时 */
export function computeCumulative(timeline: TimelineBlock[]): CumulativeInfo {
  const toolCumulative = new Map<string, number>();
  const parallelCumulative = new Map<string, number>();
  let cumulative = 0;

  for (const block of timeline) {
    if (block.type === "tool") {
      if (block.status === "done" && block.duration_ms !== undefined) {
        cumulative += block.duration_ms;
      }
      toolCumulative.set(block.id, cumulative);
    } else if (block.type === "parallel") {
      const batchStart = cumulative;
      for (const child of block.children) {
        if (child.type === "tool") {
          const afterBatch =
            block.duration_ms !== undefined
              ? batchStart + block.duration_ms
              : batchStart;
          toolCumulative.set(child.id, afterBatch);
        }
      }
      if (block.duration_ms !== undefined) {
        cumulative = batchStart + block.duration_ms;
      }
      parallelCumulative.set(block.batch_id, cumulative);
    }
  }

  return { toolCumulative, parallelCumulative };
}
/** 按 path/url 去重来源列表 */
export function dedupeSources(sources: SourceRef[]): SourceRef[] {
  const seen = new Set<string>();
  const out: SourceRef[] = [];
  for (const s of sources) {
    const key =
      s.type === "kb"
        ? `kb:${s.path}`
        : s.type === "conversation"
          ? `conversation:${s.cid}:${s.message_id}:${s.start_char}:${s.end_char}`
          : `${s.type}:${s.url}`;
    if (!seen.has(key)) {
      seen.add(key);
      out.push(s);
    }
  }
  return out;
}
/** 与后端 `_title_from_text` 对齐：取首行，最长 40 字。 */
export function titleFromText(text: string): string {
  const line = text.trim().split("\n")[0] ?? "";
  if (line.length > 40) return `${line.slice(0, 40)}…`;
  return line || "新对话";
}
