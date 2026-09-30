import { useState } from "react";
import type { CatalogGroup, ScrollTarget } from "./requestInspectorGroups";
import { categoryColor } from "../requestCategories";
import { compactTokenCount } from "../../../utils/chatMessageFormat";
import { FoldChevron } from "../../FoldChevron";

type Props = {
  groups: CatalogGroup[];
  categoryFilter: string | null;
  onNavigate: (target: ScrollTarget) => void;
};

export function RequestInspectorCatalog({
  groups,
  categoryFilter,
  onNavigate,
}: Props) {
  const [open, setOpen] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    for (const g of groups) init[g.id] = g.defaultOpen;
    return init;
  });

  return (
    <div className="reqinspector-catalog-inner">
      {groups.map((group) => {
        const isOpen = open[group.id] ?? group.defaultOpen;
        return (
          <section key={group.id} className="reqinspector-cat-group">
            <button
              type="button"
              className="reqinspector-cat-group-head"
              onClick={() =>
                setOpen((s) => ({ ...s, [group.id]: !isOpen }))
              }
              aria-expanded={isOpen}
            >
              <FoldChevron open={isOpen} size={10} />
              <span>{group.title}</span>
            </button>
            {isOpen ? (
              <div className="reqinspector-cat-group-body">
                {group.lines.map((line) => {
                  const dim =
                    categoryFilter != null && line.category !== categoryFilter;
                  return (
                    <button
                      key={line.id}
                      type="button"
                      className={`reqinspector-cat-row${dim ? " is-dim" : ""}`}
                      onClick={() => onNavigate(line.target)}
                    >
                      <span
                        className="reqinspector-dot"
                        style={{ background: categoryColor(line.category) }}
                      />
                      <span className="reqinspector-cat-label">
                        {line.summary ? `${line.label} · ${line.summary}` : line.label}
                      </span>
                      <span className="reqinspector-cat-tok">
                        ≈{compactTokenCount(line.tokens)}
                      </span>
                    </button>
                  );
                })}
              </div>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}
