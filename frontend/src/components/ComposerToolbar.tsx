import type { ChangeEvent, RefObject } from "react";
import { ModelPickerButton } from "./chat/ModelPickerButton";
import { ContextStatsButton } from "./chat/ContextStatsButton";

type Props = {
  webEnabled: boolean;
  onToggleWeb: () => void;
  streaming: boolean;
  canSend: boolean;
  conversationId: string | null;
  onAttachClick: () => void;
  onSend: () => void;
  onStop?: () => void;
  fileInputRef: RefObject<HTMLInputElement | null>;
  onFileChange: (e: ChangeEvent<HTMLInputElement>) => void;
};

function GlobeIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden
    >
      <circle cx="12" cy="12" r="10" />
      <path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 19V5M5 12l7-7 7 7" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden
    >
      <rect x="6" y="6" width="12" height="12" rx="1" />
    </svg>
  );
}

export function ComposerToolbar({
  webEnabled,
  onToggleWeb,
  streaming,
  canSend,
  conversationId,
  onAttachClick,
  onSend,
  onStop,
  fileInputRef,
  onFileChange,
}: Props) {
  return (
    <div className="composer-toolbar">
      <div className="composer-toolbar-left">
        <button
          type="button"
          className="composer-icon-btn composer-attach-btn"
          onClick={onAttachClick}
          title="添加附件"
          aria-label="添加附件"
        >
          <PlusIcon />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          hidden
          multiple
          accept="image/*,video/mp4,video/webm,video/quicktime,video/mpeg"
          onChange={onFileChange}
        />
        <button
          type="button"
          className={`composer-icon-btn composer-web-btn${webEnabled ? " composer-web-btn--on" : ""}`}
          onClick={onToggleWeb}
          aria-pressed={webEnabled}
          aria-label={webEnabled ? "联网搜索：开" : "联网搜索：关"}
          title={
            webEnabled
              ? "联网搜索：开（本地优先，联网补充）"
              : "联网搜索：关（仅本地知识库）"
          }
        >
          <GlobeIcon />
        </button>
      </div>
      <div className="composer-toolbar-right">
        <ContextStatsButton conversationId={conversationId} />
        <ModelPickerButton />
        {streaming && onStop ? (
          <button
            type="button"
            className="composer-send-btn composer-send-btn--stop"
            onClick={onStop}
            title="停止生成"
            aria-label="停止生成"
          >
            <StopIcon />
          </button>
        ) : null}
        <button
          type="button"
          className={`composer-send-btn${canSend ? " composer-send-btn--ready" : ""}`}
          onClick={onSend}
          disabled={!canSend}
          title={streaming ? "加入发送队列 (Enter)" : "发送 (Enter)"}
          aria-label={streaming ? "加入队列" : "发送"}
        >
          <SendIcon />
        </button>
      </div>
    </div>
  );
}
