import { visit } from "unist-util-visit";

/** GFM 自动链接会把 **、全角括号及后续中文误并入 href，需在 AST 层截断。 */
export function trimAutolinkUrl(raw: string): string {
  let s = raw;
  const trailingJunk =
    /(?:\*\*|[_*]|[\u4e00-\u9fff（）「」【】，。；：！？、'"「\s<>])$/u;
  while (s.length > "https://".length && trailingJunk.test(s)) {
    s = s.slice(0, -1);
  }
  return s;
}

type LinkNode = {
  url?: string;
  children?: { type: string; value?: string }[];
};

/** 在 remark-gfm 之后运行，修正自动链接的 url 与可见文本。 */
export function remarkTrimAutolinkUrls() {
  return (tree: Parameters<typeof visit>[0]) => {
    visit(tree, "link", (node: LinkNode) => {
      if (!node.url) return;
      const trimmed = trimAutolinkUrl(node.url);
      if (trimmed === node.url) return;
      node.url = trimmed;
      const child = node.children?.[0];
      if (
        node.children?.length === 1 &&
        child?.type === "text" &&
        typeof child.value === "string" &&
        child.value.startsWith("http")
      ) {
        child.value = trimmed;
      }
    });
  };
}
