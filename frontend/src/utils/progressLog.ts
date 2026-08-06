/** 工具 progress_log 噪音行（心跳等）。 */
export function isNoiseProgressLine(line: string): boolean {
  return /^仍在运行…/.test((line || "").trim());
}
