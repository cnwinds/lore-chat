/** 工具时间线条目的 query 字段：写入时统一截断（与后端 clip_tool_query 对齐）。 */
export const TOOL_QUERY_MAX_CHARS = 1024;

export function clipToolQuery(
  text: string,
  maxChars: number = TOOL_QUERY_MAX_CHARS,
): string {
  const s = text.trim();
  if (!s) return "";
  return s.length > maxChars ? `${s.slice(0, maxChars)}…` : s;
}

/** 旧版后端会把 `$ <command>` 写入 progress；仅在与 query 同源时剥掉。 */
export function stripLegacyEchoedPrompt(output: string, cmd: string): string {
  if (!cmd || !output.startsWith("$ ")) return output;
  const nl = output.indexOf("\n");
  const echoed = (nl >= 0 ? output.slice(2, nl) : output.slice(2)).replace(
    /\r$/,
    "",
  );
  const withoutEllipsis = (s: string) => s.replace(/(?:…|\.\.\.)$/, "");
  const echoedStem = withoutEllipsis(echoed);
  const cmdStem = withoutEllipsis(cmd);
  const same =
    echoed === cmd ||
    (echoedStem.length > 0 &&
      cmdStem.length > 0 &&
      (echoedStem.startsWith(cmdStem) || cmdStem.startsWith(echoedStem)));
  if (!same) return output;
  return nl >= 0 ? output.slice(nl + 1) : "";
}
