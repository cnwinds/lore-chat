/**
 * SSE 时间线观测：server timeline_state 合并 + ephemeral updateTimeline reduce。
 * ADR 2026-08-08 §5 的前端半。
 */

import { appendProgressChunk } from "./progressLog";
import { clipToolQuery } from "./toolQuery";
import { resolveToolLabel } from "./toolLabels";
import { resolveToolStartedAtMs } from "./toolDuration";
import type {
  ChatMessage,
  DocContextItem,
  QuestionOption,
  SourceRef,
  TimelineBlock,
} from "../types/chat";

function toolQueryFromInput(input: unknown): string | undefined {
  if (!input || typeof input !== "object") return undefined;
  const o = input as Record<string, unknown>;
  for (const key of ["query", "prompt", "command", "path", "sandbox_path"]) {
    const v = o[key];
    if (typeof v === "string" && v.trim()) {
      return clipToolQuery(v);
    }
  }
  return undefined;
}

function findActiveParallelIndex(timeline: TimelineBlock[]): number {
  for (let i = timeline.length - 1; i >= 0; i--) {
    const block = timeline[i];
    if (block.type === "parallel" && block.duration_ms === undefined) {
      return i;
    }
  }
  return -1;
}

function updateToolBlock(
  blocks: TimelineBlock[],
  id: string,
  updater: (block: Extract<TimelineBlock, { type: "tool" }>) => TimelineBlock,
): TimelineBlock[] {
  return blocks.map((block) => {
    if (block.type === "tool" && block.id === id) {
      return updater(block);
    }
    if (block.type === "parallel") {
      return {
        ...block,
        children: updateToolBlock(block.children, id, updater),
      };
    }
    return block;
  });
}

export function updateTimeline(
  timeline: TimelineBlock[],
  event: string,
  data: Record<string, unknown>,
): TimelineBlock[] {
  if (event === "tool_start") {
    const query = toolQueryFromInput(data.input);
    const toolBlock: TimelineBlock = {
      type: "tool",
      id: data.id as string,
      tool: data.tool as string,
      label:
        (data.label as string) ||
        resolveToolLabel(
          data.tool as string,
          (data.input as Record<string, unknown> | undefined) ?? null,
        ),
      ts: data.ts as string,
      status: "running",
      started_at_ms: resolveToolStartedAtMs(data.ts as string) ?? Date.now(),
      ...(query ? { query } : {}),
    };
    const parallelIdx = findActiveParallelIndex(timeline);
    if (parallelIdx >= 0) {
      return timeline.map((block, i) =>
        i === parallelIdx && block.type === "parallel"
          ? { ...block, children: [...block.children, toolBlock] }
          : block,
      );
    }
    return [...timeline, toolBlock];
  }

  if (event === "tool_progress") {
    const id = data.id as string;
    const message = typeof data.message === "string" ? data.message : "";
    if (!message) return timeline;
    return updateToolBlock(timeline, id, (block) => {
      const next = appendProgressChunk(block.progress_log, message);
      if (next === block.progress_log) {
        return block;
      }
      const previewSrc = message.trim();
      const preview =
        previewSrc.length > 0
          ? previewSrc.length < 200
            ? previewSrc
            : `${previewSrc.slice(0, 200)}…`
          : block.summary;
      return {
        ...block,
        progress_log: next,
        ...(preview ? { summary: preview } : {}),
      };
    });
  }

  if (event === "tool_result") {
    const id = data.id as string;
    return updateToolBlock(timeline, id, (block) => {
      const next = {
        ...block,
        status: "done" as const,
        summary: (data.summary as string) || "",
        sources: (data.sources as SourceRef[]) || [],
        ...(data.content ? { content: data.content as string } : {}),
        ...(data.duration_ms !== undefined
          ? { duration_ms: data.duration_ms as number }
          : {}),
        ...(typeof data.query === "string" && data.query.trim()
          ? { query: (data.query as string).trim() }
          : {}),
        ...(data.question_id
          ? { question_id: data.question_id as string }
          : {}),
        ...(data.question ? { question: data.question as string } : {}),
        ...(data.options
          ? { options: data.options as QuestionOption[] }
          : {}),
        ...(data.multi_select !== undefined
          ? { multi_select: data.multi_select as boolean }
          : {}),
        ...(typeof data.preview === "string" && data.preview
          ? { preview: data.preview as string }
          : {}),
        ...(typeof data.reindex_mode === "string" && data.reindex_mode
          ? { reindex_mode: data.reindex_mode as string }
          : {}),
        ...(data.applied !== undefined
          ? { applied: data.applied as number }
          : {}),
        ...(Array.isArray(data.attachments)
          ? { attachments: data.attachments as string[] }
          : {}),
      };
      // 生图轮询文案仅运行时有用；完成后与同步厂商一致
      if (block.tool === "generate_image") {
        delete next.progress_log;
      }
      return next;
    });
  }

  if (event === "parallel_batch_start") {
    const parallelBlock: TimelineBlock = {
      type: "parallel",
      batch_id: data.batch_id as string,
      ts: data.ts as string,
      children: [],
    };
    return [...timeline, parallelBlock];
  }

  if (event === "parallel_batch_end") {
    const batchId = data.batch_id as string;
    return timeline.map((block) =>
      block.type === "parallel" && block.batch_id === batchId
        ? {
            ...block,
            ...(data.duration_ms !== undefined
              ? { duration_ms: data.duration_ms as number }
              : {}),
          }
        : block,
    );
  }

  if (event === "think_delta") {
    const delta = (data.delta as string) || "";
    const last = timeline[timeline.length - 1];
    if (last?.type === "think") {
      return [
        ...timeline.slice(0, -1),
        { ...last, content: last.content + delta },
      ];
    }
    return [
      ...timeline,
      { type: "think", ts: data.ts as string, content: delta },
    ];
  }

  if (event === "text_delta") {
    const delta = (data.delta as string) || "";
    const last = timeline[timeline.length - 1];
    if (last?.type === "text") {
      return [
        ...timeline.slice(0, -1),
        { ...last, content: last.content + delta },
      ];
    }
    return [
      ...timeline,
      { type: "text", ts: data.ts as string, content: delta },
    ];
  }

  if (event === "user_inject") {
    const injectId = (data.inject_id as string) || "";
    return [
      ...timeline,
      {
        type: "user_inject",
        inject_id: injectId,
        ts: (data.ts as string) || new Date().toISOString(),
        text: (data.text as string) || "",
        ...(typeof data.message_id === "string"
          ? { message_id: data.message_id }
          : {}),
        ...(typeof data.client_message_id === "string"
          ? { client_message_id: data.client_message_id }
          : {}),
        ...(Array.isArray(data.doc_context)
          ? { doc_context: data.doc_context as DocContextItem[] }
          : {}),
        ...(typeof data.primary_doc === "string"
          ? { primary_doc: data.primary_doc }
          : {}),
        ...(Array.isArray(data.attachments)
          ? { attachments: data.attachments as string[] }
          : {}),
      },
    ];
  }

  return timeline;
}

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
        // 切会话后 prev 无本地锚点；用服务端 ts 回填。非法 ts 不打 Date.now()，避免秒表归零。
        const started = resolveToolStartedAtMs(
          b.ts,
          prevById.get(b.id) ?? b.started_at_ms,
        );
        return started != null ? { ...b, started_at_ms: started } : b;
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

/** Ephemeral / 兼容路径别名。 */
export function applyTimelineEvent(
  timeline: TimelineBlock[],
  event: string,
  data: Record<string, unknown>,
): TimelineBlock[] {
  return updateTimeline(timeline, event, data);
}
