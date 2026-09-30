import { useCallback, useEffect, useRef, useState } from "react";
import { getContextStats, type ContextStats } from "../../api";
import { FixedOverflowMenu } from "../FixedOverflowMenu";
import { compactTokenCount } from "../../utils/chatMessageFormat";
import { categoryColor } from "./requestCategories";
import { RequestInspectorModal } from "./request-inspector/RequestInspectorModal";

type Props = {
  conversationId: string | null;
  streaming?: boolean;
};

/** 圆环：总量为实测 prompt tokens；>80% 时预警色。 */
function ContextRing({ used, limit }: { used: number | null; limit: number | null }) {
  const size = 20;
  const stroke = 2.4;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = used != null && limit ? Math.min(1, used / limit) : 0;
  const progressColor = pct > 0.8 ? "var(--accent)" : "var(--glaze)";
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="var(--border)"
        strokeWidth={stroke}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={progressColor}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={`${c * pct} ${c}`}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
    </svg>
  );
}

/** 输入条右侧统计环：弹层看容量与分项估算；「查看发送内容」打开最近一次请求快照。 */
export function ContextStatsButton({ conversationId, streaming = false }: Props) {
  const [open, setOpen] = useState(false);
  const [stats, setStats] = useState<ContextStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [inspectorCategory, setInspectorCategory] = useState<string | null>(null);
  const anchorRef = useRef<HTMLButtonElement>(null);
  const wasStreaming = useRef(false);

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
    void load();
  }, [load]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  useEffect(() => {
    if (wasStreaming.current && !streaming) {
      void load();
    }
    wasStreaming.current = streaming;
  }, [streaming, load]);

  if (!conversationId) return null;

  const used = stats?.context.used_tokens ?? null;
  const limit = stats?.context.limit_tokens ?? null;
  const pct = used != null && limit ? (used / limit) * 100 : null;
  const hasCapture = (stats?.segments?.length ?? 0) > 0 || stats?.latest_call_id != null;
  const barDenominator = limit ?? used;
  const barSegments = (stats?.segments ?? []).filter(
    (seg) => seg.tokens > 0 && barDenominator,
  );

  const openInspector = (category: string | null) => {
    setOpen(false);
    setInspectorCategory(category);
    setInspectorOpen(true);
  };

  return (
    <>
      <button
        ref={anchorRef}
        type="button"
        className="composer-icon-btn ctxstats-ring-btn"
        onClick={() => setOpen((v) => !v)}
        title={pct != null ? `会话统计：上下文 ${pct.toFixed(1)}%` : "会话统计"}
        aria-label="会话统计"
        aria-expanded={open}
      >
        <ContextRing used={used} limit={limit} />
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
              <span
                className={`ctxstats-pct${pct != null && pct > 80 ? " ctxstats-pct--warn" : ""}`}
              >
                {pct != null ? `${pct.toFixed(1)}%` : "—"}
              </span>
              <button
                type="button"
                className="ctxstats-link"
                onClick={() => openInspector(null)}
              >
                查看发送内容
              </button>
            </div>
            <div className="ctxstats-used">
              {used != null
                ? `${compactTokenCount(used)}${limit ? ` / ${compactTokenCount(limit)}` : ""}`
                : "暂无用量的模型调用"}
            </div>
            {hasCapture ? (
              <>
                <div className="ctxstats-bar-track">
                  {barSegments.map((seg) => {
                    const width =
                      barDenominator && barDenominator > 0
                        ? (seg.tokens / barDenominator) * 100
                        : 0;
                    return (
                      <div
                        key={seg.key}
                        className="ctxstats-bar-seg"
                        style={{
                          width: `${width}%`,
                          background: categoryColor(seg.key),
                        }}
                      />
                    );
                  })}
                </div>
                <div className="ctxstats-section">
                  {stats.segments.map((seg) => {
                    const segPct =
                      used != null && used > 0 ? (seg.tokens / used) * 100 : null;
                    return (
                      <button
                        key={seg.key}
                        type="button"
                        className="ctxstats-row ctxstats-row--peek"
                        onClick={() => openInspector(seg.key)}
                        title="按实测总量分摊的估算"
                      >
                        <span className="ctxstats-row-label">
                          <span
                            className="ctxstats-dot"
                            style={{ background: categoryColor(seg.key) }}
                          />
                          {seg.label}
                        </span>
                        <span className="ctxstats-row-value">
                          ≈{compactTokenCount(seg.tokens)}
                          {segPct != null ? ` · ${segPct.toFixed(0)}%` : ""}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </>
            ) : (
              <p className="ctxstats-hint">发出消息后显示</p>
            )}
            <div className="ctxstats-section ctxstats-rows">
              {stats.cache_hit_rate != null && (
                <div className="ctxstats-row">
                  <span className="ctxstats-row-label">缓存命中</span>
                  <span className="ctxstats-row-value">
                    {(stats.cache_hit_rate * 100).toFixed(0)}%
                  </span>
                </div>
              )}
              <div className="ctxstats-row">
                <span className="ctxstats-row-label">工具调用</span>
                <span className="ctxstats-row-value">{stats.tool_calls}</span>
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
                  <span className="ctxstats-row-value ctxstats-row-value--full">
                    {stats.model}
                  </span>
                </div>
              )}
            </div>
          </>
        ) : null}
      </FixedOverflowMenu>
      <RequestInspectorModal
        open={inspectorOpen}
        conversationId={conversationId}
        initialCategory={inspectorCategory}
        initialCallId={stats?.latest_call_id ?? "latest"}
        onClose={() => setInspectorOpen(false)}
      />
    </>
  );
}
