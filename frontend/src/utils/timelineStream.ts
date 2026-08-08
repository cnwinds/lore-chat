/**
 * SSE 时间线观测：server timeline_state 合并 + ephemeral updateTimeline 委托。
 * ADR 2026-08-08 §5 的前端半：持久回合以后端投影为准，保留 started_at_ms。
 */

import {
  updateTimeline,
  type ChatMessage,
  type TimelineBlock,
} from "../api";

export function mergeServerTimeline(
  prev: ChatMessage,
  incoming: TimelineBlock[],
  assistantText?: string,
): ChatMessage {
  const prevById = new Map<string, number>();
  const walk = (blocks: TimelineBlock[]) => {
    for (const b of blocks) {
      if (b.type === "tool" && typeof b.started_at_ms === "number") {
        prevById.set(b.id, b.started_at_ms);
      } else if (b.type === "parallel") {
        walk(b.children);
      }
    }
  };
  walk(prev.timeline ?? []);
  const merge = (blocks: TimelineBlock[]): TimelineBlock[] =>
    blocks.map((b) => {
      if (b.type === "tool") {
        const started = prevById.get(b.id) ?? b.started_at_ms ?? Date.now();
        return { ...b, started_at_ms: started };
      }
      if (b.type === "parallel") {
        return { ...b, children: merge(b.children) };
      }
      return b;
    });
  return {
    ...prev,
    timeline: merge(incoming),
    ...(assistantText !== undefined ? { text: assistantText } : {}),
  };
}

/** Ephemeral / 兼容路径：委托 api.updateTimeline。 */
export function applyTimelineEvent(
  timeline: TimelineBlock[],
  event: string,
  data: Record<string, unknown>,
): TimelineBlock[] {
  return updateTimeline(timeline, event, data);
}
