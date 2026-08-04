import { useEffect, useState } from "react";

type Props = {
  open: boolean;
  initialDirectory: string;
  initialFilename: string;
  submitting: boolean;
  onClose: () => void;
  onConfirm: (directory: string, filename: string) => void;
};

export function ArchiveConversationModal({
  open,
  initialDirectory,
  initialFilename,
  submitting,
  onClose,
  onConfirm,
}: Props) {
  const [directory, setDirectory] = useState(initialDirectory);
  const [filename, setFilename] = useState(initialFilename);

  useEffect(() => {
    if (open) {
      setDirectory(initialDirectory);
      setFilename(initialFilename);
    }
  }, [open, initialDirectory, initialFilename]);

  if (!open) return null;

  const canSubmit =
    !submitting && directory.trim().length > 0 && filename.trim().endsWith(".md");

  return (
    <div className="snippet-modal-backdrop" onClick={submitting ? undefined : onClose}>
      <div
        className="snippet-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="archive-modal-title"
      >
        <header className="snippet-modal-header">
          <h3 id="archive-modal-title">归档到知识库</h3>
          <button
            type="button"
            className="snippet-modal-close"
            onClick={onClose}
            disabled={submitting}
          >
            ×
          </button>
        </header>
        <div className="snippet-modal-body">
          <p className="archive-modal-hint">
            指定目录与文件名（须以 .md 结尾），与 Agent 工具 summarize_conversation 一致。
          </p>
          <label className="archive-modal-field">
            <span>目录</span>
            <input
              type="text"
              value={directory}
              onChange={(e) => setDirectory(e.target.value)}
              placeholder="如 未分类 或 技术/笔记"
              disabled={submitting}
              autoFocus
            />
          </label>
          <label className="archive-modal-field">
            <span>文件名</span>
            <input
              type="text"
              value={filename}
              onChange={(e) => setFilename(e.target.value)}
              placeholder="如 会话纪要.md"
              disabled={submitting}
            />
          </label>
        </div>
        <footer className="snippet-modal-footer">
          <button type="button" onClick={onClose} disabled={submitting}>
            取消
          </button>
          <button
            type="button"
            disabled={!canSubmit}
            onClick={() => onConfirm(directory.trim(), filename.trim())}
          >
            {submitting ? "归档中…" : "开始归档"}
          </button>
        </footer>
      </div>
    </div>
  );
}
