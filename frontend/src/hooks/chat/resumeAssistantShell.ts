import type { ChatMessage } from "../../api";
import { nowIsoDisplay } from "../../utils/displayTime";

export function buildResumeAssistantPatch(
  base: ChatMessage[],
  speakerId?: string | null,
): { messages: ChatMessage[]; streamingIndex: number } {
  const last = base[base.length - 1];
  const sid = (speakerId || "").trim();
  const lastSid = (last?.speaker_id || "").trim();
  const sameSpeaker =
    last?.role === "assistant" && (sid ? lastSid === sid : true);
  if (sameSpeaker) {
    return { messages: base, streamingIndex: Math.max(0, base.length - 1) };
  }
  const next: ChatMessage = {
    role: "assistant",
    ts: nowIsoDisplay(),
    timeline: [],
    sources: [],
    ...(sid ? { speaker_kind: "role" as const, speaker_id: sid } : {}),
  };
  return { messages: [...base, next], streamingIndex: base.length };
}
