import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { remarkTrimAutolinkUrls } from "../utils/markdownAutolink";
import { rewriteMarkdownImageSrcsForDisplay } from "../utils/kbImageUrls";

type Props = {
  children: string;
  className?: string;
};

/**
 * 通用 Markdown 渲染（聊天时间线等）。
 * - 相对路径插图 → /api/download
 */
export function MarkdownContent({ children, className }: Props) {
  const md = rewriteMarkdownImageSrcsForDisplay(children);

  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkTrimAutolinkUrls]}>
        {md}
      </ReactMarkdown>
    </div>
  );
}
