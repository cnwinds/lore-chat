/** 列表里用任务说明首行当标题，避免整段提示词撑开右栏。 */
export function routineListTitle(prompt: string, max = 28): string {
  const line = prompt.trim().split(/\r?\n/, 1)[0]?.trim() || "未命名任务";
  if (line.length <= max) return line;
  return `${line.slice(0, max).trimEnd()}…`;
}
