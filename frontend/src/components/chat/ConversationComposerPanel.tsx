import { type ReactNode, type RefObject } from "react";
import type { DocTrayItem, PendingFile } from "../../types/composer";
import type { SendQueueItem } from "../../utils/sendQueue";
import { ComposerSendQueue } from "../ComposerSendQueue";
import { ComposerTray } from "../ComposerTray";
import { ComposerToolbar } from "../ComposerToolbar";

const INPUT_MIN_HEIGHT = 34;
const INPUT_MAX_HEIGHT = 160;

type Props = {
  conversationId: string | null;
  sendQueueItems: SendQueueItem[];
  sendQueuePaused: boolean;
  onContinue: () => void;
  onRetry: () => void;
  onSkipFailed: () => void;
  onUpdateQueueText: (id: string, text: string) => void;
  onSetQueueTiming: (id: string, timing: SendQueueItem["timing"]) => void;
  onGuideQueueItem: (id: string) => void;
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
  onCaretSync?: () => void;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  mentionSlot?: ReactNode;
  mentionOpen?: boolean;
  mentionListId?: string;
  mentionActiveId?: string;
  webEnabled: boolean;
  onToggleWeb: () => void;
  streaming: boolean;
  canSend: boolean;
  onAttachClick: () => void;
  onSend: () => void;
  onStop: () => void;
  fileInputRef: RefObject<HTMLInputElement | null>;
  onFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
};

/** 会话输入区：发送队列 + 文档托盘 + 文本框 + 工具栏。 */
export function ConversationComposerPanel({
  conversationId,
  sendQueueItems,
  sendQueuePaused,
  onContinue,
  onRetry,
  onSkipFailed,
  onUpdateQueueText,
  onSetQueueTiming,
  onGuideQueueItem,
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
  onCaretSync,
  textareaRef,
  mentionSlot = null,
  mentionOpen = false,
  mentionListId,
  mentionActiveId,
  webEnabled,
  onToggleWeb,
  streaming,
  canSend,
  onAttachClick,
  onSend,
  onStop,
  fileInputRef,
  onFileChange,
}: Props) {
  return (
    <div className="chat-composer-wrap">
      <div className="composer-card-stack">
        {mentionSlot}
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
          <ComposerSendQueue
            items={sendQueueItems}
            paused={sendQueuePaused}
            onContinue={onContinue}
            onRetry={onRetry}
            onSkipFailed={onSkipFailed}
            onUpdateText={onUpdateQueueText}
            onSetTiming={onSetQueueTiming}
            onGuide={onGuideQueueItem}
            onToggleMerge={onToggleQueueMerge}
            onRemove={onRemoveQueueItem}
            onMove={onMoveQueueItem}
            onSetAllTiming={onSetAllQueueTiming}
            onSetAllMerge={onSetAllQueueMerge}
            onClear={onClearQueue}
          />
          <div className="composer-body">
            <div className="composer-input">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => onInputChange(e.target.value)}
                onKeyDown={onInputKeyDown}
                onPaste={onInputPaste}
                onSelect={onCaretSync}
                onClick={onCaretSync}
                onKeyUp={onCaretSync}
                rows={1}
                placeholder={
                  sendQueueItems.length > 0
                    ? "继续输入以排队…"
                    : streaming
                      ? "输入消息加入队列…"
                      : "输入消息…"
                }
                title="Enter 发送，Shift+Enter 换行；可粘贴本地文件或图片到托盘"
                aria-expanded={mentionOpen}
                aria-controls={mentionOpen ? mentionListId : undefined}
                aria-activedescendant={mentionOpen ? mentionActiveId : undefined}
                aria-autocomplete="list"
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
              conversationId={conversationId}
              onAttachClick={onAttachClick}
              onSend={onSend}
              onStop={onStop}
              fileInputRef={fileInputRef}
              onFileChange={onFileChange}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
