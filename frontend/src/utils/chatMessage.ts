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

export function isInjectedUserMessage(m: ChatMessage): boolean {
  return (
    m.role === "user" &&
    (!!m.injected ||
      (!!m.client_message_id && m.client_message_id.startsWith("inject:")))
  );
}

function toolBlockAwaitsUser(
  block: Extract<TimelineBlock, { type: "tool" }>,
): boolean {
  const confirmTool =
    block.tool === "ask_user" || block.tool === "sandbox_run";
  return (
    confirmTool &&
    block.status === "done" &&
    !block.choice_resolved &&
    !!block.question_id &&
    Array.isArray(block.options) &&
    block.options.length > 0
  );
}

/** True when the turn left an unanswered ask_user prompt. */
export function timelineAwaitsUserAnswer(
  timeline: TimelineBlock[] | undefined,
): boolean {
  if (!timeline?.length) return false;
  for (const block of timeline) {
    if (block.type === "tool" && toolBlockAwaitsUser(block)) return true;
    if (block.type === "parallel") {
      for (const child of block.children) {
        if (child.type === "tool" && toolBlockAwaitsUser(child)) return true;
      }
    }
  }
  return false;
}

/** 刷新/重载后：把仍标 running 的工具收成 interrupted，避免永远转圈。 */
export function normalizeLoadedTimeline(
  timeline: TimelineBlock[] | undefined,
): TimelineBlock[] | undefined {
  if (!timeline?.length) return timeline;

  function patch(block: TimelineBlock): TimelineBlock {
    if (block.type === "tool" && block.status === "running") {
      return {
        ...block,
        status: "interrupted",
        summary: block.summary || "连接中断，未完成",
      };
    }
    if (block.type === "parallel") {
      return { ...block, children: block.children.map(patch) };
    }
    return block;
  }
  return timeline.map(patch);
}

export function normalizeLoadedMessage(m: ChatMessage): ChatMessage {
  if (!m.timeline?.length) return m;
  const timeline = normalizeLoadedTimeline(m.timeline);
  if (!timeline || timeline === m.timeline) return m;
  const hasInterrupted = timeline.some(
    (b) =>
      (b.type === "tool" && b.status === "interrupted") ||
      (b.type === "parallel" &&
        b.children.some((c) => c.type === "tool" && c.status === "interrupted")),
  );
  return {
    ...m,
    timeline,
    status: m.status === "interrupted" || hasInterrupted ? "interrupted" : m.status,
  };
}

export type ChatDisplayRow = {
  key: string;
  message: ChatMessage;
  /** Index in the original msgs array (for live-streaming detection). */
  sourceIndex: number;
  /** Last assistant slice of a split turn keeps sources/meta. */
  isTailSlice: boolean;
};

/**
 * Expand assistant timelines that contain mid-turn user_inject blocks into
 * interleaved assistant segments + standalone user bubbles, in stream order.
 * Standalone DB inject user rows are skipped (shown via timeline expansion).
 */
export function expandMessagesForDisplay(msgs: ChatMessage[]): ChatDisplayRow[] {
  const rows: ChatDisplayRow[] = [];
  for (let i = 0; i < msgs.length; i++) {
    const m = msgs[i];
    if (isInjectedUserMessage(m)) continue;

    if (m.role !== "assistant" || !m.timeline?.some((b) => b.type === "user_inject")) {
      rows.push({
        key: `${m.id ?? m.ts ?? "msg"}-${i}`,
        message: m,
        sourceIndex: i,
        isTailSlice: true,
      });
      continue;
    }

    const timeline = m.timeline;
    let segment: TimelineBlock[] = [];
    let part = 0;

    const flushAssistant = (blocks: TimelineBlock[], isTail: boolean) => {
      if (!blocks.length && !isTail) return;
      if (!blocks.length && isTail) {
        // Empty trailing slice: still show if sources-only / live shell.
        if (!m.sources?.length && !m.text) return;
      }
      rows.push({
        key: `${m.id ?? m.ts ?? "msg"}-${i}-a${part}`,
        message: {
          ...m,
          timeline: blocks,
          text: isTail ? m.text : undefined,
          sources: isTail ? m.sources : undefined,
          total_duration_ms: isTail ? m.total_duration_ms : undefined,
        },
        sourceIndex: i,
        isTailSlice: isTail,
      });
      part += 1;
    };

    for (const block of timeline) {
      if (block.type === "user_inject") {
        flushAssistant(segment, false);
        segment = [];
        rows.push({
          key: `${m.id ?? m.ts ?? "msg"}-${i}-inj-${block.inject_id}`,
          message: {
            id: block.message_id,
            role: "user",
            text: block.text,
            ts: block.ts,
            injected: true,
            client_message_id:
              block.client_message_id ?? `inject:${block.inject_id}`,
            ...(block.doc_context ? { doc_context: block.doc_context } : {}),
            ...(block.primary_doc ? { primary_doc: block.primary_doc } : {}),
            ...(block.attachments ? { attachments: block.attachments } : {}),
          },
          sourceIndex: i,
          isTailSlice: true,
        });
        continue;
      }
      segment.push(block);
    }
    flushAssistant(segment, true);
  }
  return rows;
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
