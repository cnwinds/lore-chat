import type { SendQueueItem, QueueTiming } from "../utils/sendQueue";

type Props = {
  items: SendQueueItem[];
  paused: boolean;
  onContinue: () => void;
  onRetry: () => void;
  onSkipFailed: () => void;
  onUpdateText: (id: string, text: string) => void;
  onSetTiming: (id: string, timing: QueueTiming) => void;
  onToggleMerge: (id: string) => void;
  onRemove: (id: string) => void;
  onMove: (id: string, direction: -1 | 1) => void;
  onSetAllTiming: (timing: QueueTiming) => void;
  onSetAllMerge: (merge: boolean) => void;
  onClear: () => void;
};

function preview(text: string, max = 48): string {
  const t = text.trim().replace(/\s+/g, " ");
  if (t.length <= max) return t;
  return `${t.slice(0, max)}…`;
}

export function ComposerSendQueue({
  items,
  paused,
  onContinue,
  onRetry,
  onSkipFailed,
  onUpdateText,
  onSetTiming,
  onToggleMerge,
  onRemove,
  onMove,
  onSetAllTiming,
  onSetAllMerge,
  onClear,
}: Props) {
  if (!items.length) return null;

  const hasError = items.some((x) => x.error);

  return (
    <div className="composer-send-queue" role="region" aria-label="发送队列">
      <div className="composer-send-queue-toolbar">
        <span className="composer-send-queue-title">
          队列 {items.length}
          {paused ? " · 已暂停" : ""}
        </span>
        <div className="composer-send-queue-actions">
          {paused && (
            <button type="button" className="composer-queue-btn" onClick={onContinue}>
              继续发送
            </button>
          )}
          {hasError && (
            <>
              <button type="button" className="composer-queue-btn" onClick={onRetry}>
                重试
              </button>
              <button type="button" className="composer-queue-btn" onClick={onSkipFailed}>
                跳过失败
              </button>
            </>
          )}
          <button
            type="button"
            className="composer-queue-btn"
            onClick={() => onSetAllTiming("defer")}
          >
            全部 defer
          </button>
          <button
            type="button"
            className="composer-queue-btn"
            onClick={() => onSetAllTiming("inject")}
          >
            全部 inject
          </button>
          <button
            type="button"
            className="composer-queue-btn"
            onClick={() => onSetAllMerge(true)}
          >
            全部合并
          </button>
          <button type="button" className="composer-queue-btn" onClick={onClear}>
            清空
          </button>
        </div>
      </div>
      <ul className="composer-send-queue-list">
        {items.map((item, index) => (
          <li
            key={item.id}
            className={`composer-send-queue-item${item.locked ? " is-locked" : ""}${item.error ? " is-error" : ""}`}
          >
            <div className="composer-send-queue-item-main">
              {item.locked ? (
                <span className="composer-send-queue-text" title={item.text}>
                  {preview(item.text)}（注入中）
                </span>
              ) : (
                <input
                  className="composer-send-queue-edit"
                  value={item.text}
                  onChange={(e) => onUpdateText(item.id, e.target.value)}
                  aria-label="排队消息"
                />
              )}
              {item.error && (
                <span className="composer-send-queue-error" title={item.error}>
                  {item.error}
                </span>
              )}
            </div>
            <div className="composer-send-queue-item-controls">
              <select
                value={item.timing}
                disabled={!!item.locked}
                onChange={(e) =>
                  onSetTiming(item.id, e.target.value as QueueTiming)
                }
                aria-label="发送时机"
              >
                <option value="defer">回合后</option>
                <option value="inject">插入本轮</option>
              </select>
              {index < items.length - 1 && (
                <label className="composer-queue-merge">
                  <input
                    type="checkbox"
                    checked={item.mergeWithNext}
                    disabled={!!item.locked}
                    onChange={() => onToggleMerge(item.id)}
                  />
                  与下一条合并
                </label>
              )}
              <button
                type="button"
                className="composer-queue-btn"
                disabled={!!item.locked || index === 0}
                onClick={() => onMove(item.id, -1)}
                aria-label="上移"
              >
                ↑
              </button>
              <button
                type="button"
                className="composer-queue-btn"
                disabled={!!item.locked || index === items.length - 1}
                onClick={() => onMove(item.id, 1)}
                aria-label="下移"
              >
                ↓
              </button>
              <button
                type="button"
                className="composer-queue-btn"
                disabled={!!item.locked}
                onClick={() => onRemove(item.id)}
                aria-label="删除"
              >
                ×
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
