import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { listShares, revokeShare, type ShareLinkItem } from "../../api/share";
import { useCopyShareUrl } from "../../hooks/useShareLink";
import { showToast } from "../../utils/toast";

type Filter = "all" | "conversation" | "doc";

function formatExp(exp: string | null): { text: string; tone: "ok" | "warn" | "muted" } {
  if (!exp) return { text: "永久有效", tone: "muted" };
  const ms = Date.parse(exp);
  if (!Number.isFinite(ms)) return { text: exp, tone: "muted" };
  if (ms <= Date.now()) return { text: "已过期", tone: "warn" };
  const diff = ms - Date.now();
  const days = Math.floor(diff / 86400000);
  if (days >= 1) return { text: `${days} 天后过期`, tone: "ok" };
  const hours = Math.floor(diff / 3600000);
  if (hours >= 1) return { text: `${hours} 小时后过期`, tone: "ok" };
  return { text: "即将过期", tone: "warn" };
}

function formatCreated(iso: string): string {
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return iso;
  return new Date(ms).toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function ShareSettingsTab() {
  const copyUrl = useCopyShareUrl();
  const [items, setItems] = useState<ShareLinkItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const copiedTimerRef = useRef<number | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (copiedTimerRef.current != null) {
        window.clearTimeout(copiedTimerRef.current);
      }
    };
  }, []);

  const reload = useCallback((opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    setError(null);
    listShares()
      .then((res) => {
        if (!mountedRef.current) return;
        setItems(res.shares.filter((s) => !s.revoked));
      })
      .catch((e: unknown) => {
        if (!mountedRef.current) return;
        setError(e instanceof Error ? e.message : "加载失败");
        setItems([]);
      })
      .finally(() => {
        if (mountedRef.current) setLoading(false);
      });
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const filtered = useMemo(() => {
    if (filter === "all") return items;
    return items.filter((i) => i.type === filter);
  }, [items, filter]);

  const handleCopy = async (item: ShareLinkItem) => {
    if (!item.url) return;
    const ok = await copyUrl(item.url);
    if (!ok || !mountedRef.current) return;
    setCopiedId(item.share_id);
    showToast("链接已复制");
    if (copiedTimerRef.current != null) {
      window.clearTimeout(copiedTimerRef.current);
    }
    copiedTimerRef.current = window.setTimeout(() => {
      if (mountedRef.current) setCopiedId(null);
      copiedTimerRef.current = null;
    }, 2000);
  };

  const handleRevoke = async (shareId: string) => {
    if (!window.confirm("确定撤销此分享链接？访客将无法再访问。")) return;
    try {
      await revokeShare(shareId);
      showToast("已撤销分享");
      reload({ silent: true });
    } catch (e: unknown) {
      if (mountedRef.current) {
        setError(e instanceof Error ? e.message : "撤销失败");
      }
    }
  };

  const handleOpen = (item: ShareLinkItem) => {
    if (item.url) {
      window.open(item.url, "_blank", "noopener,noreferrer");
    }
  };

  if (loading) {
    return (
      <div className="share-mgmt share-mgmt--loading">
        <div className="share-mgmt-skeleton" />
        <div className="share-mgmt-skeleton share-mgmt-skeleton--short" />
      </div>
    );
  }

  return (
    <div className="share-mgmt">
      <header className="share-mgmt-header">
        <div>
          <h3 className="share-mgmt-title">分享链接</h3>
          <p className="share-mgmt-lead">
            管理已创建的公开链接，可随时复制或撤销访问。
          </p>
        </div>
        <button
          type="button"
          className="share-mgmt-refresh"
          onClick={() => reload({ silent: true })}
          title="刷新列表"
          aria-label="刷新列表"
        >
          ↻
        </button>
      </header>

      {error ? <p className="share-mgmt-error">{error}</p> : null}

      {!items.length ? (
        <div className="share-mgmt-empty">
          <span className="share-mgmt-empty-icon" aria-hidden />
          <p className="share-mgmt-empty-title">暂无有效分享</p>
          <p className="share-mgmt-empty-hint">
            在对话工具栏或文档预览菜单中创建分享链接后，会显示在这里。
          </p>
        </div>
      ) : (
        <>
          <div className="share-mgmt-toolbar">
            <div className="share-mgmt-filters" role="tablist" aria-label="按类型筛选">
              {(
                [
                  { id: "all", label: "全部" },
                  { id: "conversation", label: "对话" },
                  { id: "doc", label: "文档" },
                ] as const
              ).map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  role="tab"
                  aria-selected={filter === opt.id}
                  className={`share-mgmt-filter${filter === opt.id ? " share-mgmt-filter--active" : ""}`}
                  onClick={() => setFilter(opt.id)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <p className="share-mgmt-count">
              {filtered.length}
              {filter === "all" ? "" : ` / ${items.length}`} 个
            </p>
          </div>
          {!filtered.length ? (
            <p className="share-mgmt-empty-filter">当前筛选下没有分享链接</p>
          ) : (
            <ul className="share-mgmt-list">
              {filtered.map((item) => {
                const exp = formatExp(item.exp);
                const isDoc = item.type === "doc";
                return (
                  <li key={item.share_id} className="share-mgmt-card">
                    <div className="share-mgmt-card-top">
                      <span
                        className={`share-mgmt-badge share-mgmt-badge--${item.type}`}
                      >
                        {isDoc ? "文档" : "对话"}
                      </span>
                      <span className={`share-mgmt-exp share-mgmt-exp--${exp.tone}`}>
                        {exp.text}
                      </span>
                    </div>
                    <h4 className="share-mgmt-card-title">{item.title}</h4>
                    {isDoc && item.options.source_path ? (
                      <p className="share-mgmt-card-path">{item.options.source_path}</p>
                    ) : null}
                    <dl className="share-mgmt-meta">
                      <dt>创建</dt>
                      <dd>{formatCreated(item.created_at)}</dd>
                      <dt>访问</dt>
                      <dd>{item.view_count} 次</dd>
                      {isDoc && item.options.pin_version !== undefined ? (
                        <>
                          <dt>版本</dt>
                          <dd>{item.options.pin_version ? "已固定" : "跟随文档"}</dd>
                        </>
                      ) : null}
                    </dl>
                    <div className="share-mgmt-card-actions">
                      <button
                        type="button"
                        className="share-mgmt-btn"
                        disabled={!item.url}
                        onClick={() => handleOpen(item)}
                      >
                        打开
                      </button>
                      <button
                        type="button"
                        className="share-mgmt-btn share-mgmt-btn--primary"
                        disabled={!item.url}
                        onClick={() => void handleCopy(item)}
                      >
                        {copiedId === item.share_id ? "已复制" : "复制链接"}
                      </button>
                      <button
                        type="button"
                        className="share-mgmt-btn share-mgmt-btn--danger"
                        onClick={() => void handleRevoke(item.share_id)}
                      >
                        撤销
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
