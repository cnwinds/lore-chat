import { useState } from "react";
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

function IconPencil() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
    </svg>
  );
}

function IconCheck() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M20 6L9 17l-5-5" />
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

function IconGrip() {
  return (
    <svg width="10" height="14" viewBox="0 0 10 14" fill="currentColor" aria-hidden>
      <circle cx="2.5" cy="2.5" r="1.3" />
      <circle cx="7.5" cy="2.5" r="1.3" />
      <circle cx="2.5" cy="7" r="1.3" />
      <circle cx="7.5" cy="7" r="1.3" />
      <circle cx="2.5" cy="11.5" r="1.3" />
      <circle cx="7.5" cy="11.5" r="1.3" />
    </svg>
  );
}

/** 二态时机签：引导=移到队首并注入当前信息流（accent 提示）；排队=回合后再发。 */
function TimingPill({
  value,
  disabled,
  onGuide,
  onQueue,
}: {
  value: QueueTiming;
  disabled?: boolean;
  onGuide: () => void;
  onQueue: () => void;
}) {
  const inject = value === "inject";
  return (
    <button
      type="button"
      className={`composer-queue-timing${inject ? " is-inject" : ""}`}
      disabled={disabled}
      onClick={() => (inject ? onQueue() : onGuide())}
      title={inject ? "引导中：注入当前信息流（点击改回排队）" : "排队中：点击引导到队首并插入当前信息流"}
      aria-label={inject ? "引导中：注入当前信息流" : "排队中"}
      aria-pressed={inject}
    >
      {inject ? "引导" : "排队"}
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
  onRemove,
  onMove,
  onClear,
}: Props) {
  const [dragId, setDragId] = useState<string | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);

  if (!items.length) return null;

  const hasError = items.some((x) => x.error);

  function moveToIndex(from: number, target: number) {
    const dir: -1 | 1 = target > from ? 1 : -1;
    const steps = Math.abs(target - from);
    for (let i = 0; i < steps; i++) onMove(items[from].id, dir);
  }

  /** 引导：把该条移到队首并注入当前信息流 */
  function guideItem(item: SendQueueItem, index: number) {
    onSetTiming(item.id, "inject");
    if (index > 0) moveToIndex(index, 0);
  }

  return (
    <div className="composer-send-queue" role="region" aria-label="发送队列">
      {(paused || hasError) && (
        <div className="composer-send-queue-bar">
          {paused && <span className="composer-queue-flag">已暂停</span>}
          {hasError && <span className="composer-queue-flag is-error">发送失败</span>}
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
              className="composer-queue-icon-btn"
              onClick={onClear}
              title="清空队列"
              aria-label="清空"
            >
              <IconTrash />
            </button>
          </div>
        </div>
      )}

      <ul className="composer-send-queue-list">
        {items.map((item, index) => (
          <li
            key={item.id}
            className={`composer-send-queue-slot${dragOverIndex === index && dragId !== item.id ? " is-drag-over" : ""}`}
            onDragOver={(e) => {
              if (!dragId || dragId === item.id) return;
              e.preventDefault();
              setDragOverIndex(index);
            }}
            onDrop={(e) => {
              e.preventDefault();
              const from = items.findIndex((x) => x.id === dragId);
              if (from >= 0 && from !== index) moveToIndex(from, index);
              setDragId(null);
              setDragOverIndex(null);
            }}
          >
            <div
              className={`composer-send-queue-row${item.locked ? " is-locked" : ""}${item.error ? " is-error" : ""}`}
            >
              <span
                className="composer-queue-grip"
                title="拖动排序"
                aria-hidden
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.effectAllowed = "move";
                  e.dataTransfer.setData("text/plain", item.id);
                  setDragId(item.id);
                }}
                onDragEnd={() => {
                  setDragId(null);
                  setDragOverIndex(null);
                }}
              >
                <IconGrip />
              </span>
              {item.locked ? (
                <span className="composer-send-queue-text" title={item.text}>
                  <IconSpinner />
                  <span>{item.text.trim() || "注入中…"}</span>
                </span>
              ) : editingId === item.id ? (
                <input
                  className="composer-send-queue-edit"
                  value={item.text}
                  onChange={(e) => onUpdateText(item.id, e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === "Escape") {
                      setEditingId(null);
                    }
                  }}
                  onBlur={() => setEditingId(null)}
                  autoFocus
                  aria-label={`编辑队列消息 ${index + 1}`}
                  placeholder="排队消息…"
                />
              ) : (
                <span
                  className="composer-send-queue-text composer-send-queue-text--clickable"
                  title={`${item.text || "排队消息…"}（点击编辑）`}
                  onClick={() => setEditingId(item.id)}
                >
                  <span>{item.text.trim() || "排队消息…"}</span>
                </span>
              )}
              {item.error && (
                <span className="composer-send-queue-error" title={item.error}>
                  !
                </span>
              )}
              <TimingPill
                value={item.timing}
                disabled={!!item.locked}
                onGuide={() => guideItem(item, index)}
                onQueue={() => onSetTiming(item.id, "defer")}
              />
              {!item.locked && (
                <button
                  type="button"
                  className="composer-queue-icon-btn"
                  onClick={() =>
                    setEditingId(editingId === item.id ? null : item.id)
                  }
                  title={editingId === item.id ? "完成编辑" : "编辑"}
                  aria-label={editingId === item.id ? "完成编辑" : "编辑"}
                >
                  {editingId === item.id ? <IconCheck /> : <IconPencil />}
                </button>
              )}
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
          </li>
        ))}
      </ul>
    </div>
  );
}
