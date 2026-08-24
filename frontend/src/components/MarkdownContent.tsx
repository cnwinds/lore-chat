import type { Components } from "react-markdown";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import { visit } from "unist-util-visit";
import type { Root } from "hast";
import { remarkTrimAutolinkUrls } from "../utils/markdownAutolink";
import { rewriteMarkdownImageSrcsForDisplay } from "../utils/kbImageUrls";
import {
  linkifyConversationCitations,
  parseConversationHref,
  type ConversationLinkTarget,
} from "../utils/conversationLinks";
import { splitForHighlight } from "../utils/unicodeHighlight";

/** 私有区标记：注入源文后由 rehype 换成 <mark>，不依赖 rehype-raw。 */
const MARK_START = "\uE000";
const MARK_END = "\uE001";

type Props = {
  children: string;
  className?: string;
  /** 点击正文内会话深链时跳转 */
  onOpenConversation?: (target: ConversationLinkTarget) => void;
  /** 源文字符区间高亮（跳转）；仍走 Markdown，以免丢深链/相对图 */
  highlightRange?: { start: number; end: number } | null;
};

/** 允许 conversation://（默认 urlTransform 会剥掉非 http(s) 协议）。 */
function markdownUrlTransform(url: string): string {
  if (parseConversationHref(url)) return url;
  return defaultUrlTransform(url);
}

function injectHighlightMarkers(
  text: string,
  range: { start: number; end: number },
): string {
  if (range.start >= range.end) return text;
  const { before, highlight, after } = splitForHighlight(
    text,
    range.start,
    range.end,
  );
  if (!highlight) return text;
  return `${before}${MARK_START}${highlight}${MARK_END}${after}`;
}

function rehypeHighlightMarkers() {
  return (tree: Root) => {
    visit(tree, "text", (node, index, parent) => {
      if (index == null || !parent || !("children" in parent)) return;
      const value = node.value;
      if (!value.includes(MARK_START) && !value.includes(MARK_END)) return;

      const parts: Array<
        | { type: "text"; value: string }
        | {
            type: "element";
            tagName: "mark";
            properties: { className: string[] };
            children: Array<{ type: "text"; value: string }>;
          }
      > = [];
      let rest = value;
      while (rest.length) {
        const s = rest.indexOf(MARK_START);
        const e = rest.indexOf(MARK_END);
        if (s < 0 && e < 0) {
          parts.push({ type: "text", value: rest });
          break;
        }
        if (s >= 0 && (e < 0 || s < e)) {
          if (s > 0) parts.push({ type: "text", value: rest.slice(0, s) });
          rest = rest.slice(s + MARK_START.length);
          continue;
        }
        // MARK_END
        const highlighted = rest.slice(0, e);
        parts.push({
          type: "element",
          tagName: "mark",
          properties: { className: ["message-range-highlight"] },
          children: [{ type: "text", value: highlighted }],
        });
        rest = rest.slice(e + MARK_END.length);
      }
      parent.children.splice(index, 1, ...parts);
      return index + parts.length;
    });
  };
}

/**
 * 通用 Markdown 渲染（聊天时间线等）。
 * - 相对路径插图 → /api/download
 * - conversation:// → 可点会话芯片（标题优先，不用裸 hex）
 */
export function MarkdownContent({
  children,
  className,
  onOpenConversation,
  highlightRange,
}: Props) {
  const sourced =
    highlightRange && highlightRange.start < highlightRange.end
      ? injectHighlightMarkers(children, highlightRange)
      : children;
  const md = rewriteMarkdownImageSrcsForDisplay(
    linkifyConversationCitations(sourced),
  );

  const components: Components = {
    a({ href, children: linkChildren }) {
      const target = parseConversationHref(href);
      if (target) {
        if (!onOpenConversation) {
          return (
            <span className="conversation-md-link conversation-md-link--static">
              <span className="source-link-text">{linkChildren}</span>
            </span>
          );
        }
        return (
          <button
            type="button"
            className="source-link source-link--inline conversation-md-link"
            title="打开该会话"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onOpenConversation(target);
            }}
          >
            <span className="source-link-icon" aria-hidden>
              💬
            </span>
            <span className="source-link-text">{linkChildren}</span>
          </button>
        );
      }
      if (!href) {
        return <span>{linkChildren}</span>;
      }
      return (
        <a href={href} target="_blank" rel="noopener noreferrer">
          {linkChildren}
        </a>
      );
    },
  };

  const highlightActive = !!(
    highlightRange &&
    highlightRange.start < highlightRange.end
  );
  const cls = [className, highlightActive ? "chat-markdown--jump-target" : ""]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={cls}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkTrimAutolinkUrls]}
        rehypePlugins={highlightActive ? [rehypeHighlightMarkers] : undefined}
        urlTransform={markdownUrlTransform}
        components={components}
      >
        {md}
      </ReactMarkdown>
    </div>
  );
}
