type Props = {
  open: boolean;
  title: string;
  message: string;
  existingPath?: string;
  conflictingFilename: string;
  filename: string;
  allowOverwrite?: boolean;
  onFilenameChange: (v: string) => void;
  onOverwrite: () => void;
  onRename: () => void;
  onCancel: () => void;
};

export function KbNameConflictDialog({
  open,
  title,
  message,
  existingPath,
  conflictingFilename,
  filename,
  allowOverwrite = true,
  onFilenameChange,
  onOverwrite,
  onRename,
  onCancel,
}: Props) {
  if (!open) return null;
  const trimmed = filename.trim();
  return (
    <div className="modal-backdrop" role="presentation" onClick={onCancel}>
      <div
        className="modal-panel kb-conflict-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="kb-conflict-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="kb-conflict-title">{title}</h3>
        <p className="kb-conflict-message">{message}</p>
        {existingPath ? (
          <p className="kb-conflict-path" title={existingPath}>
            位置：<code>{existingPath}</code>
          </p>
        ) : null}
        <p className="kb-conflict-hint">
          「{conflictingFilename}」已存在。可覆盖原文件，或改用新名称保存。
        </p>
        <label className="kb-conflict-label">
          新文件名
          <input
            type="text"
            value={filename}
            onChange={(e) => onFilenameChange(e.target.value)}
            autoFocus={!allowOverwrite}
            onKeyDown={(e) => {
              if (e.key === "Enter" && trimmed) onRename();
              if (e.key === "Escape") onCancel();
            }}
          />
        </label>
        <div className="modal-actions kb-conflict-actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>
            取消
          </button>
          {allowOverwrite ? (
            <button
              type="button"
              className="btn-danger"
              onClick={onOverwrite}
            >
              覆盖原文件
            </button>
          ) : null}
          <button
            type="button"
            className="btn-primary"
            disabled={!trimmed}
            onClick={onRename}
          >
            使用新名称
          </button>
        </div>
      </div>
    </div>
  );
}
