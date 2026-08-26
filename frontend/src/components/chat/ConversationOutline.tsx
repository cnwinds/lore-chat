import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { OutlineIcon } from "../DocToolbarIcons";
import { useConversationOutlineActive } from "../../hooks/useConversationOutlineActive";
import { useHoverCapable } from "../../hooks/useHoverCapable";
import { useScrollLock } from "../../hooks/useScrollLock";
import {
  buildConversationOutline,
  CONVERSATION_OUTLINE_MIN_ITEMS,
  scrollToUserQuestion,
  type ConversationOutlineItem,
} from "../../utils/conversationOutline";
import type { ChatMessage } from "../../api";

export type ConversationOutlineLayout = "rail" | "sheet";

type Props = {
  msgs: ChatMessage[];
  conversationId: string | null;
  scrollRootRef: RefObject<HTMLElement | null>;
  /** rail：桌面右侧浮条；sheet：手机底部抽屉（分享页等） */
  layout?: ConversationOutlineLayout;
};

export function ConversationOutline({
  msgs,
  conversationId,
  scrollRootRef,
  layout = "rail",
}: Props) {
  const items = useMemo(() => buildConversationOutline(msgs), [msgs]);
  const hoverCapable = useHoverCapable();
  const [hoverOpen, setHoverOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const activeItemRef = useRef<HTMLButtonElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement | null>(null);
  const sheet = layout === "sheet";

  const open = sheet
    ? pinned
    : pinned || (hoverCapable && hoverOpen);

  useEffect(() => {
    setHoverOpen(false);
    setPinned(false);
  }, [conversationId, layout]);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        setPinned(false);
        setHoverOpen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [open]);

  useScrollLock(sheet && open, scrollRootRef);

  useEffect(() => {
    if (!sheet || !open) return;
    closeBtnRef.current?.focus?.();
  }, [sheet, open]);

  const activeIndex = useConversationOutlineActive({
    items,
    scrollRootRef,
    enabled: items.length >= CONVERSATION_OUTLINE_MIN_ITEMS,
  });

  useEffect(() => {
    if (!open || activeIndex < 0) return;
    activeItemRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [open, activeIndex]);

  if (items.length < CONVERSATION_OUTLINE_MIN_ITEMS) return null;

  const handleToggle = () => {
    if (pinned) {
      setPinned(false);
      setHoverOpen(false);
    } else {
      setPinned(true);
    }
  };

  const handleClose = () => {
    setPinned(false);
    setHoverOpen(false);
  };

  const handleJump = (item: ConversationOutlineItem) => {
    scrollToUserQuestion(scrollRootRef.current, item.messageId);
    if (sheet || !pinned) {
      setHoverOpen(false);
      if (sheet) setPinned(false);
    }
  };

  const list = (
    <nav className="chat-outline-list" aria-label="会话提问导航">
      {items.map((item, i) => {
        const isActive = i === activeIndex;
        return (
          <button
            key={item.messageId}
            ref={isActive ? activeItemRef : undefined}
            type="button"
            className={`chat-outline-item${isActive ? " is-active" : ""}`}
            title={item.fullText}
            aria-current={isActive ? "location" : undefined}
            onClick={() => handleJump(item)}
          >
            <span className="chat-outline-item-index" aria-hidden>
              #{item.index}
            </span>
            <span className="chat-outline-item-text">{item.label}</span>
          </button>
        );
      })}
    </nav>
  );

  if (sheet) {
    return (
      <div className={`chat-outline chat-outline--sheet${open ? " is-open" : ""}`}>
        <button
          type="button"
          className="share-sheet-fab"
          aria-label={`打开提问导航（${items.length} 条）`}
          aria-expanded={open}
          aria-controls="chat-outline-sheet"
          onClick={handleToggle}
        >
          <OutlineIcon size={18} />
          <span className="share-sheet-fab-label">提问</span>
          <span className="share-sheet-fab-badge" aria-hidden>
            {items.length}
          </span>
        </button>
        {open && (
          <>
            <button
              type="button"
              className="share-sheet-backdrop"
              aria-label="关闭提问导航"
              onClick={handleClose}
            />
            <div
              id="chat-outline-sheet"
              className="share-sheet-panel"
              role="dialog"
              aria-modal="true"
              aria-label="会话提问导航"
            >
              <div className="share-sheet-handle" aria-hidden />
              <div className="chat-outline-panel-head share-sheet-head">
                <span>提问</span>
                <button
                  ref={closeBtnRef}
                  type="button"
                  className="share-sheet-close"
                  aria-label="关闭提问导航"
                  onClick={handleClose}
                >
                  ×
                </button>
              </div>
              <div className="share-sheet-list">{list}</div>
            </div>
          </>
        )}
      </div>
    );
  }

  return (
    <div
      className={`chat-outline${open ? " is-open" : ""}${pinned ? " is-pinned" : ""}`}
      onMouseEnter={
        hoverCapable
          ? () => {
              setHoverOpen(true);
            }
          : undefined
      }
      onMouseLeave={
        hoverCapable
          ? () => {
              if (!pinned) setHoverOpen(false);
            }
          : undefined
      }
    >
      <button
        type="button"
        className="chat-outline-handle"
        aria-label={`会话导航（${items.length} 条提问）`}
        aria-expanded={open}
        aria-controls="chat-outline-panel"
        title={
          pinned
            ? "取消固定会话导航"
            : hoverCapable
              ? "固定会话导航"
              : open
                ? "收起会话导航"
                : "打开会话导航"
        }
        onClick={handleToggle}
      >
        <OutlineIcon size={15} />
        <span className="chat-outline-handle-badge" aria-hidden>
          {items.length}
        </span>
      </button>
      {open && (
        <div
          id="chat-outline-panel"
          className="chat-outline-panel"
          role="navigation"
          aria-label="会话提问导航"
        >
          <div className="chat-outline-panel-head">
            <span>提问</span>
            {pinned && <span className="chat-outline-pinned-tag">已固定</span>}
          </div>
          {list}
        </div>
      )}
    </div>
  );
}
