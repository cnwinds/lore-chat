import { useMemo, useState } from "react";
import { resolveMergeSources } from "../api";

type Props = {
  mergeId: string;
  newPath: string;
  sourcePaths: string[];
  onDone: () => void;
};

export function MergeSourceQuestion({
  mergeId,
  newPath,
  sourcePaths,
  onDone,
}: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedCount = selected.size;
  const orderedPaths = useMemo(() => [...sourcePaths].sort((a, b) => a.localeCompare(b, "zh-CN")), [sourcePaths]);

  function togglePath(path: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  async function handleDeleteSelected() {
    if (selectedCount === 0 || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await resolveMergeSources(mergeId, [...selected]);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "处理失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="merge-modal-backdrop">
      <div className="merge-modal" onClick={(e) => e.stopPropagation()}>
        <div className="merge-modal-header">
          <h3>是否删除源文档？</h3>
        </div>
        <div className="merge-modal-body">
          <p className="merge-modal-hint">
            新文档已采用：<strong>{newPath}</strong>
          </p>
          <p className="merge-modal-hint">可选择要删除的源文档；不勾选则全部保留。</p>
          <div className="pending-options">
            {orderedPaths.map((path) => (
              <label key={path} className={`pending-option${selected.has(path) ? " selected" : ""}`}>
                <input
                  type="checkbox"
                  checked={selected.has(path)}
                  disabled={submitting}
                  onChange={() => togglePath(path)}
                />
                <span>{path}</span>
              </label>
            ))}
          </div>
          {error && <div className="merge-modal-error">{error}</div>}
        </div>
        <div className="merge-modal-footer">
          <button type="button" onClick={onDone} disabled={submitting}>
            全部保留
          </button>
          <button
            type="button"
            className="merge-modal-submit"
            onClick={() => void handleDeleteSelected()}
            disabled={selectedCount === 0 || submitting}
          >
            {submitting ? "处理中..." : `删除所选（${selectedCount}）`}
          </button>
        </div>
      </div>
    </div>
  );
}
