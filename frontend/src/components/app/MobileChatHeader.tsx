type Props = {
  title: string;
  onOpenNav: () => void;
  onNewChat: () => void;
  onShare?: () => void;
};

export function MobileChatHeader({
  title,
  onOpenNav,
  onNewChat,
  onShare,
}: Props) {
  return (
    <header className="mobile-chat-header">
      <button
        type="button"
        className="mobile-chat-header-btn"
        onClick={onOpenNav}
        aria-label="打开导航"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
          <path
            d="M4 7h16M4 12h16M4 17h16"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      </button>
      <h1 className="mobile-chat-header-title">{title}</h1>
      <div className="mobile-chat-header-actions">
        {onShare && (
          <button
            type="button"
            className="mobile-chat-header-btn"
            onClick={onShare}
            aria-label="分享对话"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path
                d="M12 3v10M8 7l4-4 4 4M5 21h14a2 2 0 0 0 2-2v-5"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
        )}
        <button
          type="button"
          className="mobile-chat-header-btn mobile-chat-header-btn--accent"
          onClick={onNewChat}
          aria-label="新对话"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M12 5v14M5 12h14"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </div>
    </header>
  );
}
