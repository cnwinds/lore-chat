import type { DocTrayItem, PendingFile } from "../types/composer";

type Props = {
  items: DocTrayItem[];
  primaryPath: string | null;
  pendingFiles: PendingFile[];
  onSetPrimary: (path: string) => void;
  onRemoveDoc: (path: string) => void;
  onRemoveFile: (id: string) => void;
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

export function ComposerTray({
  items,
  primaryPath,
  pendingFiles,
  onSetPrimary,
  onRemoveDoc,
  onRemoveFile,
}: Props) {
  if (items.length === 0 && pendingFiles.length === 0) return null;

  return (
    <div className="composer-tray">
      {items.map((item) => (
        <div
          key={item.path}
          className={`composer-doc-chip${item.path === primaryPath ? " composer-doc-chip--primary" : ""}`}
          onClick={() => onSetPrimary(item.path)}
          role="button"
          tabIndex={0}
          title={item.title}
        >
          <span className="composer-doc-chip-bar" aria-hidden />
          <span className="composer-doc-chip-title">{item.title}</span>
          <button
            type="button"
            className="composer-chip-close"
            onClick={(e) => {
              e.stopPropagation();
              onRemoveDoc(item.path);
            }}
            aria-label="移除"
          >
            ×
          </button>
        </div>
      ))}
      {pendingFiles.map((f) => (
        <div key={f.id} className="composer-file-chip" title={f.name}>
          <span className="composer-file-icon" aria-hidden>
            📄
          </span>
          <span className="composer-file-name">{f.name}</span>
          <span className="composer-file-size">{formatSize(f.size)}</span>
          <button
            type="button"
            className="composer-chip-close"
            onClick={() => onRemoveFile(f.id)}
            aria-label="移除"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
