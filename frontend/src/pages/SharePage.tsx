import { useEffect, useMemo, useRef } from "react";
import type { ChatMessage } from "../api";
import { ChatMessageList } from "../components/chat/ChatMessageList";
import { MarkdownContent } from "../components/MarkdownContent";
import { LoreLogo } from "../components/LoreLogo";
import { usePublicShare } from "../hooks/useShareLink";
import { parseDocOutline } from "../utils/docOutline";

type Props = {
  shareId: string;
};

function formatExpHint(exp: string | null): string | null {
  if (!exp) return "永久有效";
  const ms = Date.parse(exp);
  if (!Number.isFinite(ms)) return null;
  const diff = ms - Date.now();
  if (diff <= 0) return "已过期";
  const days = Math.floor(diff / (86400 * 1000));
  if (days >= 1) return `剩余约 ${days} 天`;
  const hours = Math.floor(diff / (3600 * 1000));
  if (hours >= 1) return `剩余约 ${hours} 小时`;
  return "即将过期";
}

export function SharePage({ shareId }: Props) {
  const { payload, error, loading } = usePublicShare(shareId);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    document.title = payload?.title
      ? `${payload.title} · Lore Chat 分享`
      : "Lore Chat 分享";
    const meta = document.querySelector('meta[name="robots"]');
    if (meta) {
      meta.setAttribute("content", "noindex,nofollow");
    } else {
      const el = document.createElement("meta");
      el.name = "robots";
      el.content = "noindex,nofollow";
      document.head.appendChild(el);
    }
  }, [payload?.title]);

  const expHint = payload ? formatExpHint(payload.exp) : null;

  const outlineItems = useMemo(() => {
    if (!payload || payload.type !== "doc") return [];
    return parseDocOutline(payload.body);
  }, [payload]);

  const noop = () => {};

  return (
    <div className="share-page">
      <header className="share-page-header">
        <LoreLogo variant="wordmark" className="share-page-logo" />
        <div className="share-page-meta">
          {payload && <h1 className="share-page-title">{payload.title}</h1>}
          {expHint && <p className="share-page-exp">{expHint}</p>}
        </div>
      </header>

      <main className="share-page-main">
        {loading && <div className="share-page-status">加载中…</div>}
        {!loading && error && (
          <div className="share-page-status share-page-error">{error}</div>
        )}
        {!loading && payload?.type === "conversation" && (
          <div className="share-page-chat">
            <ChatMessageList
              msgs={payload.messages as ChatMessage[]}
              loadingHistory={false}
              streaming={false}
              liveElapsedMs={0}
              streamingAssistantIdxRef={{ current: null }}
              messagesContainerRef={{ current: null }}
              messagesEndRef={messagesEndRef}
              conversationId={null}
              onOpenSource={noop}
              onQuestionResolved={noop}
              readOnly
            />
          </div>
        )}
        {!loading && payload?.type === "doc" && (
          <div className="share-page-doc">
            {outlineItems.length > 0 && (
              <aside className="share-page-outline">
                <div className="share-page-outline-title">大纲</div>
                <ul>
                  {outlineItems.map((item, i) => (
                    <li key={`${item.text}-${i}`} style={{ paddingLeft: (item.level - 1) * 12 }}>
                      <a href={`#${item.id}`}>{item.text}</a>
                    </li>
                  ))}
                </ul>
              </aside>
            )}
            <article className="share-page-doc-body markdown-body">
              <MarkdownContent>{payload.body}</MarkdownContent>
            </article>
          </div>
        )}
      </main>

      <footer className="share-page-footer">
        此内容为只读分享 · 由 Lore Chat 生成
      </footer>
    </div>
  );
}
