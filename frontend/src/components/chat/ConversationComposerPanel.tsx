import { type RefObject } from "react";
import type { DocTrayItem, PendingFile } from "../../types/composer";
import type { SendQueueItem } from "../../utils/sendQueue";
import { ComposerSendQueue } from "../ComposerSendQueue";
import { ComposerTray } from "../ComposerTray";
import { ComposerToolbar } from "../ComposerToolbar";

const INPUT_MIN_HEIGHT = 34;
const INPUT_MAX_HEIGHT = 160;

type Props = {
  sendQueueItems: SendQueueItem[];
  sendQueuePaused: boolean;
  onContinue: () => void;
  onRetry: () => void;
  onSkipFailed: () => void;
  onUpdateQueueText: (id: string, text: string) => void;
  onSetQueueTiming: (id: string, timing: SendQueueItem["timing"]) => void;
  onToggleQueueMerge: (id: string) => void;
  onRemoveQueueItem: (id: string) => void;
  onMoveQueueItem: (id: string, direction: -1 | 1) => void;
  onSetAllQueueTiming: (timing: SendQueueItem["timing"]) => void;
  onSetAllQueueMerge: (merge: boolean) => void;
  onClearQueue: () => void;
  docTrayItems: DocTrayItem[];
  primaryDocPath: string | null;
  pendingFiles: PendingFile[];
  composerMediaHints: string[];
  onTraySetPrimary: (path: string) => void;
  onTrayRemove: (path: string) => void;
  onRemovePendingFile: (id: string) => void;
  input: string;
  onInputChange: (value: string) => void;
  onInputKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  onInputPaste: (e: React.ClipboardEvent<HTMLTextAreaElement>) => void;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
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
  onOpenSummary: (path: string) => void;
  onAttachClick: () => void;
  onSend: () => void;
  onStop: () => void;
  fileInputRef: RefObject<HTMLInputElement | null>;
  onFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onShare?: () => void;
};

/** 会话输入区：发送队列 + 文档托盘 + 文本框 + 工具栏。 */
export function ConversationComposerPanel({
  sendQueueItems,
  sendQueuePaused,
  onContinue,
  onRetry,
  onSkipFailed,
  onUpdateQueueText,
  onSetQueueTiming,
  onToggleQueueMerge,
  onRemoveQueueItem,
  onMoveQueueItem,
  onSetAllQueueTiming,
  onSetAllQueueMerge,
  onClearQueue,
  docTrayItems,
  primaryDocPath,
  pendingFiles,
  composerMediaHints,
  onTraySetPrimary,
  onTrayRemove,
  onRemovePendingFile,
  input,
  onInputChange,
  onInputKeyDown,
  onInputPaste,
  textareaRef,
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
  onStop,
  fileInputRef,
  onFileChange,
  onShare,
}: Props) {
  return (
    <div className="chat-composer-wrap">
      <ComposerSendQueue
        items={sendQueueItems}
        paused={sendQueuePaused}
        onContinue={onContinue}
        onRetry={onRetry}
        onSkipFailed={onSkipFailed}
        onUpdateText={onUpdateQueueText}
        onSetTiming={onSetQueueTiming}
        onToggleMerge={onToggleQueueMerge}
        onRemove={onRemoveQueueItem}
        onMove={onMoveQueueItem}
        onSetAllTiming={onSetAllQueueTiming}
        onSetAllMerge={onSetAllQueueMerge}
        onClear={onClearQueue}
      />
      <div className="composer-card">
        <ComposerTray
          items={docTrayItems}
          primaryPath={primaryDocPath}
          pendingFiles={pendingFiles}
          mediaCapabilityHints={composerMediaHints}
          onSetPrimary={onTraySetPrimary}
          onRemoveDoc={onTrayRemove}
          onRemoveFile={onRemovePendingFile}
        />
        <div className="composer-body">
          <div className="composer-input">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => onInputChange(e.target.value)}
              onKeyDown={onInputKeyDown}
              onPaste={onInputPaste}
              rows={1}
              placeholder={streaming ? "输入消息加入队列…" : "输入消息…"}
              title="Enter 发送，Shift+Enter 换行；可粘贴本地文件或图片到托盘"
              style={{
                minHeight: INPUT_MIN_HEIGHT,
                maxHeight: INPUT_MAX_HEIGHT,
              }}
            />
          </div>
          <ComposerToolbar
            webEnabled={webEnabled}
            onToggleWeb={onToggleWeb}
            streaming={streaming}
            canSend={canSend}
            archiving={archiving}
            conversationId={conversationId}
            summarized={summarized}
            summaryPath={summaryPath}
            canArchive={canArchive}
            onArchive={onArchive}
            onOpenSummary={onOpenSummary}
            onAttachClick={onAttachClick}
            onSend={onSend}
            onStop={onStop}
            fileInputRef={fileInputRef}
            onFileChange={onFileChange}
            onShare={onShare}
          />
        </div>
      </div>
    </div>
  );
}
