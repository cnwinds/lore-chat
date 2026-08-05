import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { remarkTrimAutolinkUrls } from "../utils/markdownAutolink";

type Props = {
  children: string;
  className?: string;
};

export function MarkdownContent({ children, className }: Props) {
  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkTrimAutolinkUrls]}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
