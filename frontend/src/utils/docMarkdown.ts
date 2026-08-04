/** 比较文档是否「实质修改」，忽略 Crepe/模型 Markdown 的常见表面差异。 */
export function normalizeMarkdownForCompare(text: string): string {
  let s = text
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+$/gm, "")
    // 有序列表：模型常写 `N\.`，Crepe 序列化为 `N.`
    .replace(/^(\d+)\\\.(\s)/gm, "$1.$2")
    // 无序列表：Crepe 常把 `-` 写成 `*`
    .replace(/^(\s*)[*+](\s)/gm, "$1-$2");

  // Crepe 常在列表项之间插入空行
  s = s.replace(/(^- .+)\n+(?=^- )/gm, "$1\n");
  s = s.replace(/(^\d+\. .+)\n+(?=^\d+\. )/gm, "$1\n");

  return s
    .replace(/\n{3,}/g, "\n\n")
    .replace(/\n{2,}/g, "\n\n")
    .trimEnd();
}

export function isDocMarkdownDirty(current: string, saved: string): boolean {
  if (current === saved) return false;
  return (
    normalizeMarkdownForCompare(current) !== normalizeMarkdownForCompare(saved)
  );
}

export function isMarkdownCosmeticallyEqual(a: string, b: string): boolean {
  return !isDocMarkdownDirty(a, b);
}
