import { useEffect, useMemo, useRef, useState } from "react";
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

function errorCopy(status: number, message: string): { title: string; body: string } {
  if (status === 410) {
    return {
      title: "分享已过期",
      body: "此链接的有效期已结束，内容不再对外可见。如需继续分享，请联系原作者重新创建。",
    };
  }
  if (status === 404) {
    return {
      title: "分享不可用",
      body: "链接不存在，或已被作者撤销。",
    };
  }
  return {
    title: "无法打开分享",
    body: message || "请稍后重试，或向原作者确认链接是否有效。",
  };
}

export function SharePage({ shareId }: Props) {
  const {
    payload,
    error,
    loading,
    needsPassword,
    unlocking,
    unlockError,
    submitPassword,
  } = usePublicShare(shareId);
  const [password, setPassword] = useState("");
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    document.title = payload?.title
      ? `${payload.title} · Lore Chat 分享`
      : needsPassword
        ? "需要密码 · Lore Chat 分享"
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
  }, [payload?.title, needsPassword]);

  const expHint = payload ? formatExpHint(payload.exp) : null;

  const outlineItems = useMemo(() => {
    if (!payload || payload.type !== "doc") return [];
    return parseDocOutline(payload.body).map((item, index) => ({
      ...item,
      id: `outline-${index}`,
    }));
  }, [payload]);

  const errView = error ? errorCopy(error.status, error.message) : null;
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
        {!loading && needsPassword && (
          <form
            className="share-page-unlock"
            onSubmit={(e) => {
              e.preventDefault();
              if (!password.trim() || unlocking) return;
              void submitPassword(password.trim());
            }}
          >
            <p className="share-page-unlock-title">需要访问密码</p>
            <p className="share-page-unlock-hint">此分享受密码保护，请输入密码后继续查看。</p>
            <label className="share-page-unlock-field">
              <span className="visually-hidden">访问密码</span>
              <input
                type="password"
                className="share-page-unlock-input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                autoFocus
                placeholder="访问密码"
                disabled={unlocking}
              />
            </label>
            {unlockError ? (
              <p className="share-page-unlock-error" role="alert">
                {unlockError}
              </p>
            ) : null}
            <button
              type="submit"
              className="btn-primary share-page-unlock-submit"
              disabled={unlocking || password.trim().length < 4}
            >
              {unlocking ? "验证中…" : "解锁"}
            </button>
          </form>
        )}
        {!loading && !needsPassword && errView && (
          <div className="share-page-error-card" role="alert">
            <p className="share-page-error-title">{errView.title}</p>
            <p className="share-page-error-body">{errView.body}</p>
            {error?.status === 410 ? (
              <p className="share-page-error-code">HTTP 410</p>
            ) : null}
          </div>
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
              <MarkdownContent outlineHeadingIds>{payload.body}</MarkdownContent>
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
