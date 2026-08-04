const INVALID = /[/\\?%*:|"<>]/g;

/** 归档对话框默认路径：优先沿用已有 summary_path，否则从首条用户消息推断文件名。 */
export function suggestArchivePath(
  summaryPath: string | null | undefined,
  firstUserText: string,
): { directory: string; filename: string } {
  if (summaryPath?.trim()) {
    const norm = summaryPath.replace(/\\/g, "/").replace(/^\/+/, "");
    const idx = norm.lastIndexOf("/");
    if (idx === -1) {
      return { directory: "未分类", filename: norm.endsWith(".md") ? norm : `${norm}.md` };
    }
    const directory = norm.slice(0, idx) || "未分类";
    const filename = norm.slice(idx + 1);
    return { directory, filename };
  }
  let stem = firstUserText.trim().replace(INVALID, "").slice(0, 40);
  if (!stem) stem = "会话归档";
  const filename = stem.endsWith(".md") ? stem : `${stem}.md`;
  return { directory: "未分类", filename };
}
