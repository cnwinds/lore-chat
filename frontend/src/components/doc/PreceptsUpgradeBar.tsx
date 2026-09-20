type Props = {
  proposing: boolean;
  busy: string | null;
  onReview: () => void;
  onDismiss: () => void;
};

export function PreceptsUpgradeBar({
  proposing,
  busy,
  onReview,
  onDismiss,
}: Props) {
  const locked = busy !== null;
  return (
    <footer className="doc-precepts-bar">
      <span>{proposing ? "戒律更新，正在对照…" : "戒律更新"}</span>
      <div className="doc-precepts-bar-actions">
        <button type="button" onClick={onDismiss} disabled={locked}>
          保持现行
        </button>
        <button
          type="button"
          className="doc-precepts-bar-accept"
          onClick={onReview}
          disabled={locked}
        >
          对照
        </button>
      </div>
    </footer>
  );
}
