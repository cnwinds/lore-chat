/** 工具 progress_log 噪音行（心跳等）。 */
export function isNoiseProgressLine(line: string): boolean {
  return /^仍在运行…/.test((line || "").trim());
}

const ANSI_OSC = /\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)/g;
const ANSI_CSI = /\x1b\[[0-9;?]*[ -/]*[@-~]/g;
const ANSI_OTHER = /\x1b./g;
const REDRAW_CSI = /\x1b\[[0-9;]*[GJK]/g;
const PROGRESS_LINE =
  /(?:Downloading|Rendering|Uploading|Progress|◐|◓|◑|◒|█|░|\d+(?:\.\d+)?%)/i;

/** 把终端重绘序列映射为 \\r，并剥离其余 ANSI；保留 \\r / \\n。 */
export function sanitizeControls(message: string): string {
  if (!message) return message;
  let text = message.replace(/\r\n/g, "\n");
  text = text.replace(REDRAW_CSI, "\r");
  text = text.replace(ANSI_OSC, "");
  text = text.replace(ANSI_CSI, "");
  text = text.replace(ANSI_OTHER, "");
  return text;
}

/** 在每一逻辑行内应用 \\r 覆盖写。 */
export function applyCarriageReturns(text: string): string {
  if (!text || !text.includes("\r")) return text;
  const ended = text.endsWith("\n");
  const out = text.split("\n").map((line) => {
    if (!line.includes("\r")) return line;
    let cur = "";
    for (const piece of line.split("\r")) {
      cur = piece.length >= cur.length ? piece : piece + cur.slice(piece.length);
    }
    return cur;
  });
  let result = out.join("\n");
  if (ended && !result.endsWith("\n")) result += "\n";
  return result;
}

function progressFingerprint(line: string): string {
  return line
    .replace(/[\d.]+/g, "0")
    .replace(/[◐◓◑◒✓]/g, "")
    .trim();
}

/** 连续同类进度行只留最后一条（兼容已落库的刷屏数据）。 */
export function collapseRepeatedProgress(text: string): string {
  if (!text || !text.includes("\n")) return text;
  const ended = text.endsWith("\n");
  const lines = text.split("\n");
  const out: string[] = [];
  for (const line of lines) {
    if (
      out.length &&
      line &&
      PROGRESS_LINE.test(line) &&
      PROGRESS_LINE.test(out[out.length - 1]) &&
      progressFingerprint(line) === progressFingerprint(out[out.length - 1])
    ) {
      out[out.length - 1] = line;
      continue;
    }
    out.push(line);
  }
  let result = out.join("\n");
  if (ended && !result.endsWith("\n")) result += "\n";
  return result;
}

/** 统一换行、剥 ANSI、应用 \\r、折叠进度刷屏。 */
export function normalizeStreamChunk(message: string): string {
  if (!message) return message;
  return collapseRepeatedProgress(
    applyCarriageReturns(sanitizeControls(message)),
  );
}

function needsSep(prev: string, next: string): boolean {
  if (!prev || !next) return false;
  if (/\n$/.test(prev) || /^\n/.test(next)) return false;
  return true;
}

function mergeChunk(prev: string, text: string): string {
  let base = prev;
  let chunk = text;
  if (chunk.startsWith("\r")) {
    chunk = chunk.replace(/^\r+/, "");
    const body = base.endsWith("\n") ? base.slice(0, -1) : base;
    const idx = body.lastIndexOf("\n");
    base = idx >= 0 ? body.slice(0, idx + 1) : "";
    return collapseRepeatedProgress(applyCarriageReturns(base + chunk));
  }
  const sep = needsSep(base, chunk) ? "\n" : "";
  return collapseRepeatedProgress(applyCarriageReturns(base + sep + chunk));
}

/** 追加流式块；行级无尾换行时自动补 \\n。 */
export function appendProgressChunk(
  prev: string[] | undefined,
  message: string,
): string[] {
  const text = sanitizeControls(message);
  if (!text || isNoiseProgressLine(text)) return prev ?? [];
  const base = prev ?? [];
  let next: string[];
  if (
    base.length > 0 &&
    !text.startsWith("$ ") &&
    !/^\[exit\s/.test(text.trim())
  ) {
    next = [...base.slice(0, -1), mergeChunk(base[base.length - 1], text)];
  } else {
    next = [
      ...base,
      collapseRepeatedProgress(applyCarriageReturns(text)),
    ];
  }
  const joinedLen = next.reduce((n, s) => n + s.length, 0);
  if (joinedLen > 100_000) {
    return [collapseRepeatedProgress(next.join("")).slice(-100_000)];
  }
  return next;
}

/** 展示时拼接；兼容旧「每项一行无尾换行」数据。 */
export function joinProgressChunks(chunks: string[]): string {
  if (!chunks.length) return "";
  let out = sanitizeControls(chunks[0]);
  for (let i = 1; i < chunks.length; i++) {
    out = mergeChunk(out, sanitizeControls(chunks[i]));
  }
  return collapseRepeatedProgress(applyCarriageReturns(out));
}
