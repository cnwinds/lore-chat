type Props = {
  open: boolean;
  title: string;
  message: string;
  filename: string;
  onFilenameChange: (v: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
};

export function KbNameConflictDialog({
  open,
  title,
  message,
  filename,
  onFilenameChange,
  onConfirm,
  onCancel,
}: Props) {
  if (!open) return null;
  return (
    <div className="modal-backdrop" role="presentation" onClick={onCancel}>
      <div
        className="modal-panel kb-conflict-dialog"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <h3>{title}</h3>
        <p className="kb-conflict-message">{message}</p>
        <label className="kb-conflict-label">
          文件名
          <input
            type="text"
            value={filename}
            onChange={(e) => onFilenameChange(e.target.value)}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter") onConfirm();
              if (e.key === "Escape") onCancel();
            }}
          />
        </label>
        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>
            取消
          </button>
          <button type="button" className="btn-primary" onClick={onConfirm}>
            使用该名称重试
          </button>
        </div>
      </div>
    </div>
  );
}
