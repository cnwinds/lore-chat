/** 工具 progress_log 噪音行（心跳等）。 */
export function isNoiseProgressLine(line: string): boolean {
  return /^仍在运行…/.test((line || "").trim());
}

/** 统一 \\r\\n / 孤立 \\r，避免终端显示错乱。 */
export function normalizeStreamChunk(message: string): string {
  if (!message) return message;
  return message.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
}

function needsSep(prev: string, next: string): boolean {
  if (!prev || !next) return false;
  if (/\n$/.test(prev) || /^\n/.test(next)) return false;
  return true;
}

/** 追加流式块；行级无尾换行时自动补 \\n。 */
export function appendProgressChunk(
  prev: string[] | undefined,
  message: string,
): string[] {
  const text = normalizeStreamChunk(message);
  if (!text || isNoiseProgressLine(text)) return prev ?? [];
  const base = prev ?? [];
  if (
    base.length > 0 &&
    !text.startsWith("$ ") &&
    !/^\[exit\s/.test(text.trim())
  ) {
    const last = base[base.length - 1];
    const sep = needsSep(last, text) ? "\n" : "";
    const next = [...base.slice(0, -1), last + sep + text];
    const joinedLen = next.reduce((n, s) => n + s.length, 0);
    if (joinedLen > 100_000) {
      return [next.join("").slice(-100_000)];
    }
    return next;
  }
  const next = [...base, text];
  const joinedLen = next.reduce((n, s) => n + s.length, 0);
  if (joinedLen > 100_000) {
    return [next.join("").slice(-100_000)];
  }
  return next;
}

/** 展示时拼接；兼容旧「每项一行无尾换行」数据。 */
export function joinProgressChunks(chunks: string[]): string {
  if (!chunks.length) return "";
  let out = normalizeStreamChunk(chunks[0]);
  for (let i = 1; i < chunks.length; i++) {
    const piece = normalizeStreamChunk(chunks[i]);
    const sep = needsSep(out, piece) ? "\n" : "";
    out += sep + piece;
  }
  return out;
}
