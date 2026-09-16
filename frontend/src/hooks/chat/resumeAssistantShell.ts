import type { ChatMessage } from "../../api";
import { nowIsoDisplay } from "../../utils/displayTime";

/** 无 speaker 的乐观助手泡 = 本轮壳；只有已标成别人的才另起一泡。 */
export function isSameTurnResumeAssistant(
  message: ChatMessage | undefined,
  speakerId?: string | null,
): boolean {
  if (message?.role !== "assistant") return false;
  const sid = (speakerId || "").trim();
  const lastSid = (message.speaker_id || "").trim();
  if (!sid || !lastSid) return true;
  return lastSid === sid;
}

function stampResumeAssistant(
  message: ChatMessage,
  speakerId?: string | null,
): ChatMessage {
  const sid = (speakerId || "").trim();
  if (!sid || (message.speaker_id || "").trim() === sid) {
    return message;
  }
  return {
    ...message,
    speaker_kind: "role",
    speaker_id: sid,
  };
}

function newResumeAssistant(speakerId?: string | null): ChatMessage {
  const sid = (speakerId || "").trim();
  return {
    role: "assistant",
    ts: nowIsoDisplay(),
    timeline: [],
    sources: [],
    ...(sid ? { speaker_kind: "role" as const, speaker_id: sid } : {}),
  };
}

/**
 * 断流续观测：接到本轮最后一只助手泡上，不要因缺 speaker_id 再 append。
 * 若已经叠了多只同轮助手（旧 bug / 竞态），丢掉前面的幽灵泡，只留最后一只给流式 patch。
 */
export function buildResumeAssistantPatch(
  base: ChatMessage[],
  speakerId?: string | null,
): { messages: ChatMessage[]; streamingIndex: number } {
  let end = base.length;
  while (end > 0 && isSameTurnResumeAssistant(base[end - 1], speakerId)) {
    end -= 1;
  }
  const prefix = base.slice(0, end);
  const trailing = base.slice(end);
  if (trailing.length === 0) {
    return {
      messages: [...prefix, newResumeAssistant(speakerId)],
      streamingIndex: prefix.length,
    };
  }
  const keep = stampResumeAssistant(trailing[trailing.length - 1], speakerId);
  return {
    messages: [...prefix, keep],
    streamingIndex: prefix.length,
  };
}
