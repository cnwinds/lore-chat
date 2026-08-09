import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { OutlineIcon } from "../DocToolbarIcons";
import { useConversationOutlineActive } from "../../hooks/useConversationOutlineActive";
import { useHoverCapable } from "../../hooks/useHoverCapable";
import {
  buildConversationOutline,
  CONVERSATION_OUTLINE_MIN_ITEMS,
  scrollToUserQuestion,
  type ConversationOutlineItem,
} from "../../utils/conversationOutline";
import type { ChatMessage } from "../../api";

type Props = {
  msgs: ChatMessage[];
  conversationId: string | null;
  scrollRootRef: RefObject<HTMLElement | null>;
};

export function ConversationOutline({
  msgs,
  conversationId,
  scrollRootRef,
}: Props) {
  const items = useMemo(() => buildConversationOutline(msgs), [msgs]);
  const hoverCapable = useHoverCapable();
  const [hoverOpen, setHoverOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const activeItemRef = useRef<HTMLButtonElement>(null);

  const open = pinned || (hoverCapable && hoverOpen);

  useEffect(() => {
    setHoverOpen(false);
    setPinned(false);
  }, [conversationId]);

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

  const activeIndex = useConversationOutlineActive({
    items,
    scrollRootRef,
    enabled: items.length >= CONVERSATION_OUTLINE_MIN_ITEMS,
  });

  useEffect(() => {
    if (!open || activeIndex < 0) return;
    activeItemRef.current?.scrollIntoView({ block: "nearest" });
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

  const handleJump = (item: ConversationOutlineItem) => {
    scrollToUserQuestion(scrollRootRef.current, item.messageId);
    if (!pinned) {
      setHoverOpen(false);
    }
  };

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
          <nav className="chat-outline-list">
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
        </div>
      )}
    </div>
  );
}
