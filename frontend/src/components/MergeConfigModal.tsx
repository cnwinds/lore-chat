import { useMemo, useState } from "react";
import { mergeDocs, type MergeResult } from "../api";

type Props = {
  paths: string[];
  onClose: () => void;
  onSubmit: (result: MergeResult) => void;
};

export function MergeConfigModal({ paths, onClose, onSubmit }: Props) {
  const [orderedPaths, setOrderedPaths] = useState<string[]>(paths);
  const [instruction, setInstruction] = useState("");
  const [title, setTitle] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = useMemo(() => orderedPaths.length >= 2 && !submitting, [orderedPaths, submitting]);

  function moveItem(index: number, delta: -1 | 1) {
    const nextIndex = index + delta;
    if (nextIndex < 0 || nextIndex >= orderedPaths.length) return;
    setOrderedPaths((prev) => {
      const next = [...prev];
      const [item] = next.splice(index, 1);
      next.splice(nextIndex, 0, item);
      return next;
    });
  }

  async function handleSubmit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await mergeDocs({
        paths: orderedPaths,
        order: orderedPaths,
        instruction: instruction.trim() || undefined,
        title: title.trim() || undefined,
      });
      onSubmit(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "合并失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="merge-modal-backdrop" onClick={onClose}>
      <div className="merge-modal" onClick={(e) => e.stopPropagation()}>
        <div className="merge-modal-header">
          <h3>合并文档</h3>
          <button type="button" className="merge-modal-close" onClick={onClose} disabled={submitting}>
            ×
          </button>
        </div>
        <div className="merge-modal-body">
          <p className="merge-modal-hint">已选 {orderedPaths.length} 篇，调整顺序后将按此顺序生成新文档。</p>
          <div className="merge-order-list">
            {orderedPaths.map((path, index) => (
              <div key={path} className="merge-order-item">
                <span className="merge-order-index">{index + 1}.</span>
                <span className="merge-order-path" title={path}>
                  {path}
                </span>
                <div className="merge-order-actions">
                  <button type="button" onClick={() => moveItem(index, -1)} disabled={submitting || index === 0}>
                    ↑
                  </button>
                  <button
                    type="button"
                    onClick={() => moveItem(index, 1)}
                    disabled={submitting || index === orderedPaths.length - 1}
                  >
                    ↓
                  </button>
                </div>
              </div>
            ))}
          </div>
          <label className="merge-modal-field">
            <span>文档标题（可选）</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="例如：项目综述" />
          </label>
          <label className="merge-modal-field">
            <span>合并说明（可选）</span>
            <textarea
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              placeholder="例如：按时间顺序整理，去重重复段落，并保留关键结论。"
              rows={4}
            />
          </label>
          {error && <div className="merge-modal-error">{error}</div>}
        </div>
        <div className="merge-modal-footer">
          <button type="button" onClick={onClose} disabled={submitting}>
            取消
          </button>
          <button type="button" className="merge-modal-submit" onClick={handleSubmit} disabled={!canSubmit}>
            {submitting ? "合并中..." : "开始合并"}
          </button>
        </div>
      </div>
    </div>
  );
}
