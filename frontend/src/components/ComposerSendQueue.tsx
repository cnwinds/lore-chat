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

function IconPlay() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M8 5v14l11-7z" />
    </svg>
  );
}

function IconRetry() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M21 12a9 9 0 1 1-2.6-6.2" />
      <path d="M21 3v6h-6" />
    </svg>
  );
}

function IconSkip() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M5 4l10 8-10 8V4zm11 0h3v16h-3V4z" />
    </svg>
  );
}

function IconLink() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7.1-7.1l-1.1 1.1" />
      <path d="M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7.1 7.1l1.1-1.1" />
    </svg>
  );
}

function IconTrash() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" />
    </svg>
  );
}

function IconUp() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M12 19V5M5 12l7-7 7 7" />
    </svg>
  );
}

function IconDown() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M12 5v14M19 12l-7 7-7-7" />
    </svg>
  );
}

function IconX() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  );
}

function IconSpinner() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      aria-hidden
      className="composer-queue-spin"
    >
      <path d="M12 2a10 10 0 0 1 10 10" />
    </svg>
  );
}

function TimingSwitch({
  value,
  disabled,
  onChange,
}: {
  value: QueueTiming;
  disabled?: boolean;
  onChange: (v: QueueTiming) => void;
}) {
  const inject = value === "inject";
  return (
    <button
      type="button"
      className={`composer-queue-timing${inject ? " is-inject" : " is-defer"}`}
      disabled={disabled}
      onClick={() => onChange(inject ? "defer" : "inject")}
      title={inject ? "插入本轮（点击改为回合后）" : "回合后再发（点击改为插入本轮）"}
      aria-label={inject ? "时机：插入本轮" : "时机：回合后"}
      aria-pressed={inject}
    >
      <span className="composer-queue-timing-track" aria-hidden>
        <span className="composer-queue-timing-label composer-queue-timing-label--inject">
          本轮
        </span>
        <span className="composer-queue-timing-label composer-queue-timing-label--defer">
          下回
        </span>
        <span className="composer-queue-timing-knob" />
      </span>
    </button>
  );
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
  const allMerged =
    items.length > 1 && items.slice(0, -1).every((x) => x.mergeWithNext);

  return (
    <div className="composer-send-queue" role="region" aria-label="发送队列">
      <div className="composer-send-queue-bar">
        <div className="composer-send-queue-meta">
          <span className="composer-send-queue-count">{items.length}</span>
          <span className="composer-send-queue-label">
            待发送{paused ? " · 暂停" : ""}
          </span>
        </div>
        <div className="composer-send-queue-actions">
          {paused && (
            <button
              type="button"
              className="composer-queue-icon-btn composer-queue-icon-btn--accent"
              onClick={onContinue}
              title="继续发送"
              aria-label="继续发送"
            >
              <IconPlay />
            </button>
          )}
          {hasError && (
            <>
              <button
                type="button"
                className="composer-queue-icon-btn"
                onClick={onRetry}
                title="重试失败项"
                aria-label="重试"
              >
                <IconRetry />
              </button>
              <button
                type="button"
                className="composer-queue-icon-btn"
                onClick={onSkipFailed}
                title="跳过失败项"
                aria-label="跳过失败"
              >
                <IconSkip />
              </button>
            </>
          )}
          <button
            type="button"
            className={`composer-queue-icon-btn${items.every((x) => x.timing === "inject") ? " is-active" : ""}`}
            onClick={() => onSetAllTiming("inject")}
            title="全部改为插入本轮"
            aria-label="全部插入本轮"
          >
            <span className="composer-queue-chip-text">本轮</span>
          </button>
          <button
            type="button"
            className={`composer-queue-icon-btn${items.every((x) => x.timing === "defer") ? " is-active" : ""}`}
            onClick={() => onSetAllTiming("defer")}
            title="全部改为回合后"
            aria-label="全部回合后"
          >
            <span className="composer-queue-chip-text">下回</span>
          </button>
          {items.length > 1 && (
            <button
              type="button"
              className={`composer-queue-icon-btn${allMerged ? " is-active" : ""}`}
              onClick={() => onSetAllMerge(!allMerged)}
              title={allMerged ? "取消全部合并" : "全部合并"}
              aria-label={allMerged ? "取消全部合并" : "全部合并"}
            >
              <IconLink />
            </button>
          )}
          <button
            type="button"
            className="composer-queue-icon-btn composer-queue-icon-btn--danger"
            onClick={onClear}
            title="清空队列"
            aria-label="清空"
          >
            <IconTrash />
          </button>
        </div>
      </div>

      <ul className="composer-send-queue-list">
        {items.map((item, index) => (
          <li key={item.id} className="composer-send-queue-slot">
            <div
              className={`composer-send-queue-row${item.locked ? " is-locked" : ""}${item.error ? " is-error" : ""}${item.timing === "inject" ? " is-inject" : ""}`}
            >
              <span className="composer-send-queue-index" aria-hidden>
                {index + 1}
              </span>
              {item.locked ? (
                <span className="composer-send-queue-text" title={item.text}>
                  <IconSpinner />
                  <span>{item.text.trim() || "注入中…"}</span>
                </span>
              ) : (
                <div className="composer-send-queue-body">
                  <input
                    className="composer-send-queue-edit"
                    value={item.text}
                    onChange={(e) => onUpdateText(item.id, e.target.value)}
                    aria-label={`队列消息 ${index + 1}`}
                    placeholder="排队消息…"
                  />
                  {item.error && (
                    <span
                      className="composer-send-queue-error"
                      title={item.error}
                    >
                      !
                    </span>
                  )}
                </div>
              )}
              <TimingSwitch
                value={item.timing}
                disabled={!!item.locked}
                onChange={(v) => onSetTiming(item.id, v)}
              />
              <div className="composer-send-queue-row-actions">
                <button
                  type="button"
                  className="composer-queue-icon-btn"
                  disabled={!!item.locked || index === 0}
                  onClick={() => onMove(item.id, -1)}
                  title="上移"
                  aria-label="上移"
                >
                  <IconUp />
                </button>
                <button
                  type="button"
                  className="composer-queue-icon-btn"
                  disabled={!!item.locked || index === items.length - 1}
                  onClick={() => onMove(item.id, 1)}
                  title="下移"
                  aria-label="下移"
                >
                  <IconDown />
                </button>
                <button
                  type="button"
                  className="composer-queue-icon-btn composer-queue-icon-btn--danger"
                  disabled={!!item.locked}
                  onClick={() => onRemove(item.id)}
                  title="删除"
                  aria-label="删除"
                >
                  <IconX />
                </button>
              </div>
            </div>

            {index < items.length - 1 && (
              <div className="composer-queue-bridge">
                <span className="composer-queue-bridge-line" aria-hidden />
                <button
                  type="button"
                  className={`composer-queue-bridge-btn${item.mergeWithNext ? " is-on" : ""}`}
                  disabled={!!item.locked || !!items[index + 1]?.locked}
                  onClick={() => onToggleMerge(item.id)}
                  title={
                    item.mergeWithNext
                      ? "已与下一条合并（点击取消）"
                      : "与下一条合并发送"
                  }
                  aria-label={
                    item.mergeWithNext ? "取消与下一条合并" : "与下一条合并"
                  }
                  aria-pressed={item.mergeWithNext}
                >
                  <IconLink />
                </button>
                <span className="composer-queue-bridge-line" aria-hidden />
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
