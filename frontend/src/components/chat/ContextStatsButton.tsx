import { useCallback, useEffect, useRef, useState } from "react";
import {
  getContextStats,
  type ContextStats,
} from "../../api";
import { FixedOverflowMenu } from "../FixedOverflowMenu";
import { compactTokenCount } from "../../utils/chatMessageFormat";

type Props = {
  conversationId: string | null;
};

/** 标题栏「会话统计」：容量条 + 分项占比 + 缓存命中率。 */
export function ContextStatsButton({ conversationId }: Props) {
  const [open, setOpen] = useState(false);
  const [stats, setStats] = useState<ContextStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const anchorRef = useRef<HTMLButtonElement>(null);

  const load = useCallback(async () => {
    if (!conversationId) return;
    setLoading(true);
    setError(null);
    try {
      setStats(await getContextStats(conversationId));
    } catch {
      setError("统计加载失败");
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  if (!conversationId) return null;

  const used = stats?.context.used_tokens ?? null;
  const limit = stats?.context.limit_tokens ?? null;
  const pct =
    used != null && limit ? Math.min(100, (used / limit) * 100) : null;

  return (
    <>
      <button
        ref={anchorRef}
        type="button"
        className="chat-desktop-header-btn"
        onClick={() => setOpen((v) => !v)}
        title="会话统计"
        aria-label="会话统计"
        aria-expanded={open}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
          <path
            d="M4 20V10M10 20V4M16 20v-7M22 20H2"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        </svg>
      </button>
      <FixedOverflowMenu
        open={open}
        anchorRef={anchorRef}
        align="end"
        label="会话统计"
        className="ctxstats-menu"
        onDismiss={() => setOpen(false)}
      >
        {loading && !stats ? (
          <p className="ctxstats-hint">统计中…</p>
        ) : error ? (
          <p className="ctxstats-hint">{error}</p>
        ) : stats ? (
          <>
            <div className="ctxstats-head">
              <span className="ctxstats-title">上下文容量</span>
              <span className="ctxstats-pct">
                {pct != null ? `${pct.toFixed(1)}%` : "—"}
              </span>
            </div>
            <div className="ctxstats-bar-track">
              <div
                className="ctxstats-bar-fill"
                style={{ width: `${pct ?? 0}%` }}
              />
            </div>
            <div className="ctxstats-used">
              {used != null
                ? `${compactTokenCount(used)}${limit ? ` / ${compactTokenCount(limit)}` : ""} tokens`
                : "暂无用量的模型调用"}
            </div>
            <div className="ctxstats-section">
              {stats.segments.map((seg) => {
                const segPct =
                  used != null && used > 0
                    ? (seg.tokens / used) * 100
                    : null;
                return (
                  <div key={seg.key} className="ctxstats-row">
                    <span className="ctxstats-row-label">{seg.label}</span>
                    <span className="ctxstats-row-value">
                      {compactTokenCount(seg.tokens)}
                      {segPct != null ? ` · ${segPct.toFixed(1)}%` : ""}
                    </span>
                  </div>
                );
              })}
            </div>
            <div className="ctxstats-section ctxstats-rows">
              {stats.cache_hit_rate != null && (
                <div className="ctxstats-row">
                  <span className="ctxstats-row-label">缓存命中率</span>
                  <span className="ctxstats-row-value">
                    {(stats.cache_hit_rate * 100).toFixed(1)}%
                  </span>
                </div>
              )}
              <div className="ctxstats-row">
                <span className="ctxstats-row-label">工具调用</span>
                <span className="ctxstats-row-value">
                  {stats.tool_calls} 次
                </span>
              </div>
              {stats.cost_total != null && (
                <div className="ctxstats-row">
                  <span className="ctxstats-row-label">本会话成本</span>
                  <span className="ctxstats-row-value">
                    ${stats.cost_total.toFixed(4)}
                  </span>
                </div>
              )}
              {stats.model && (
                <div className="ctxstats-row">
                  <span className="ctxstats-row-label">当前模型</span>
                  <span className="ctxstats-row-value">{stats.model}</span>
                </div>
              )}
            </div>
            <div className="ctxstats-footnote">分项为估算值，用于观察占比</div>
          </>
        ) : null}
      </FixedOverflowMenu>
    </>
  );
}
