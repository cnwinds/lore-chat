import type { SourceRef } from "../api";

type Props = {
  source: Extract<SourceRef, { type: "search" }> | null;
  onClose: () => void;
};

export function SearchSnippetModal({ source, onClose }: Props) {
  if (!source) return null;

  return (
    <div className="snippet-modal-backdrop" onClick={onClose}>
      <div
        className="snippet-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="snippet-modal-title"
      >
        <header className="snippet-modal-header">
          <h3 id="snippet-modal-title">{source.title}</h3>
          <button type="button" className="snippet-modal-close" onClick={onClose}>
            ×
          </button>
        </header>
        <div className="snippet-modal-body">
          <p>{source.snippet}</p>
          {source.provider && (
            <div className="snippet-modal-provider">来源：{source.provider}</div>
          )}
        </div>
        <footer className="snippet-modal-footer">
          {source.url && (
            <a href={source.url} target="_blank" rel="noopener noreferrer">
              打开原文
            </a>
          )}
          <button type="button" onClick={onClose}>
            关闭
          </button>
        </footer>
      </div>
    </div>
  );
}
