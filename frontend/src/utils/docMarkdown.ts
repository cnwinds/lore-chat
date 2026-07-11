/** 比较文档是否「实质修改」，忽略尾部空白、换行符差异等。 */
export function normalizeMarkdownForCompare(text: string): string {
  return text
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+$/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trimEnd();
}

export function isDocMarkdownDirty(current: string, saved: string): boolean {
  if (current === saved) return false;
  return (
    normalizeMarkdownForCompare(current) !== normalizeMarkdownForCompare(saved)
  );
}
