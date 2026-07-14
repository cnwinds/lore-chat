import type { ChangeEvent, RefObject } from "react";

type Props = {
  webEnabled: boolean;
  onToggleWeb: () => void;
  streaming: boolean;
  canSend: boolean;
  archiving: boolean;
  conversationId: string | null;
  summarized: boolean;
  summaryPath: string | null;
  canArchive: boolean;
  onArchive: () => void;
  onOpenSummary?: (path: string) => void;
  onAttachClick: () => void;
  onSend: () => void;
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

function SpinnerIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden
      className="composer-spinner"
    >
      <path d="M12 2a10 10 0 0 1 10 10" />
    </svg>
  );
}

export function ComposerToolbar({
  webEnabled,
  onToggleWeb,
  streaming,
  canSend,
  archiving,
  conversationId,
  summarized,
  summaryPath,
  canArchive,
  onArchive,
  onOpenSummary,
  onAttachClick,
  onSend,
  fileInputRef,
  onFileChange,
}: Props) {
  const archiveLinked = summarized && summaryPath;
  const archiveDisabled =
    streaming ||
    archiving ||
    !conversationId ||
    (!summarized && !canArchive);

  const handleArchiveClick = () => {
    if (archiveLinked && summaryPath && onOpenSummary) {
      onOpenSummary(summaryPath);
    } else {
      onArchive();
    }
  };

  const archiveLabel = archiving
    ? "沉淀中…"
    : archiveLinked
      ? "查看文档"
      : "沉淀";

  const archiveTitle =
    archiveLinked && summaryPath
      ? `查看归档文档：${summaryPath}`
      : "把整段会话通读后重构、去重，沉淀为一篇知识库文档";

  return (
    <div className="composer-toolbar">
      <div className="composer-toolbar-left">
        <button
          type="button"
          className="composer-icon-btn composer-attach-btn"
          onClick={onAttachClick}
          disabled={streaming}
          title="添加附件"
          aria-label="添加附件"
        >
          <PlusIcon />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          hidden
          onChange={onFileChange}
          disabled={streaming}
        />
        <button
          type="button"
          className={`composer-icon-btn composer-web-btn${webEnabled ? " composer-web-btn--on" : ""}`}
          onClick={onToggleWeb}
          disabled={streaming}
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
        <button
          type="button"
          className={`composer-archive-btn${archiveLinked ? " composer-archive-btn--linked" : ""}`}
          onClick={handleArchiveClick}
          disabled={archiveDisabled}
          title={archiveTitle}
        >
          {archiveLabel}
        </button>
        <button
          type="button"
          className={`composer-send-btn${
            streaming
              ? " composer-send-btn--busy"
              : canSend
                ? " composer-send-btn--ready"
                : ""
          }`}
          onClick={onSend}
          disabled={streaming || !canSend}
          title={streaming ? "处理中…" : "发送 (Ctrl+Enter)"}
          aria-label={streaming ? "处理中" : "发送"}
        >
          {streaming ? <SpinnerIcon /> : <SendIcon />}
        </button>
      </div>
    </div>
  );
}
