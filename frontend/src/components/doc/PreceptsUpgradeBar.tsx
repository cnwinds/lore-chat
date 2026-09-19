type Props = {
  proposing: boolean;
  busy: string | null;
  onReview: () => void;
  onConfirm: () => void;
  onDismiss: () => void;
};

export function PreceptsUpgradeBar({
  proposing,
  busy,
  onReview,
  onConfirm,
  onDismiss,
}: Props) {
  const locked = busy !== null;
  return (
    <footer className="doc-precepts-bar">
      <span>戒律更新</span>
      <div className="doc-precepts-bar-actions">
        <button type="button" onClick={onReview} disabled={locked}>
          查看
        </button>
        <button type="button" onClick={onDismiss} disabled={locked}>
          保持
        </button>
        <button
          type="button"
          className="doc-precepts-bar-accept"
          onClick={onConfirm}
          disabled={locked || proposing}
        >
          采用
        </button>
      </div>
    </footer>
  );
}
