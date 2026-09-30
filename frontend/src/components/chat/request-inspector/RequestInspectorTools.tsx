import { useState, type ReactNode } from "react";
import type { RequestTool } from "../../../api";
import { categoryColor } from "../requestCategories";
import { compactTokenCount } from "../../../utils/chatMessageFormat";
import { FoldChevron } from "../../FoldChevron";
import { highlightMatches } from "./searchHighlight";
import { textMatches, toolSearchTexts } from "./requestSearchText";

type Props = {
  tools: RequestTool[];
  categoryFilter: string | null;
  searchQuery: string;
  activeMatch: number;
  matchOffset: number;
  scrollRef?: (el: HTMLElement | null) => void;
};

export function RequestInspectorTools({
  tools,
  categoryFilter,
  searchQuery,
  activeMatch,
  matchOffset,
  scrollRef,
}: Props) {
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const dim = categoryFilter != null && categoryFilter !== "tools";
  let offset = matchOffset;

  return (
    <section
      ref={scrollRef}
      className={`reqinspector-tools${dim ? " reqinspector-tools--dim" : ""}`}
      data-scroll-kind="tools"
      aria-label={`工具定义 · ${tools.length} 个`}
    >
      <h4 className="reqinspector-tools-title">
        工具定义 · {tools.length} 个
      </h4>
      {tools.map((tool, i) => {
        const [nameText, descText, paramsText] = toolSearchTexts(tool);
        const descFirst = descText.split(/[。.!?\n]/)[0];
        const bodyHit = textMatches(descText, searchQuery) || textMatches(paramsText, searchQuery);
        const open = Boolean(expanded[i]) || bodyHit;
        const name = highlightMatches(nameText, searchQuery, activeMatch, offset);
        offset += name.matchCount;
        let descNodes: ReactNode = null;
        let paramsNodes: ReactNode = null;
        if (open) {
          const desc = highlightMatches(descText, searchQuery, activeMatch, offset);
          offset += desc.matchCount;
          const params = highlightMatches(paramsText, searchQuery, activeMatch, offset);
          offset += params.matchCount;
          descNodes = desc.nodes;
          paramsNodes = params.nodes;
        }
        return (
          <div key={tool.name || i} className="reqinspector-tool-item" data-tool-index={i}>
            <button
              type="button"
              className="reqinspector-tool-head"
              onClick={() => setExpanded((s) => ({ ...s, [i]: !open }))}
              aria-expanded={open}
            >
              <span
                className="reqinspector-dot"
                style={{ background: categoryColor("tools") }}
              />
              <span className="reqinspector-tool-name">{name.nodes}</span>
              <span className="reqinspector-tool-desc">{descFirst}</span>
              <span className="reqinspector-cat-tok">
                ≈{compactTokenCount(tool.tokens)}
              </span>
              <FoldChevron open={open} size={10} />
            </button>
            {open ? (
              <div className="reqinspector-tool-body">
                <pre className="reqinspector-seg-text">{descNodes}</pre>
                <pre className="reqinspector-seg-text">{paramsNodes}</pre>
              </div>
            ) : null}
          </div>
        );
      })}
    </section>
  );
}
