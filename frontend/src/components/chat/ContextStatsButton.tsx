import { useCallback, useEffect, useRef, useState } from "react";
import {
  getContextStats,
  type ContextStats,
  type ContextStatsSegment,
} from "../../api";
import { FixedOverflowMenu } from "../FixedOverflowMenu";
import { compactTokenCount } from "../../utils/chatMessageFormat";

type Props = {
  conversationId: string | null;
};

/** 分项配色（与后端 segments 顺序对应）：系统=琥珀、记忆=绛红、Skill=金、历史=青釉、工具=钴蓝、附件=藕紫。 */
const SEGMENT_COLORS: Record<string, string> = {
  system: "var(--system-layer)",
  memory: "var(--ctx-memory)",
  skill: "var(--ctx-skill)",
  history: "var(--glaze)",
  tools: "var(--ctx-tools)",
  attachments: "var(--ctx-att)",
};

function segmentColor(key: string): string {
  return SEGMENT_COLORS[key] ?? "var(--text-muted)";
}

/** 圆形进度环：上下文占用百分比（进度色=青釉，>80% 转朱砂预警）。 */
function ContextRing({ used, limit }: { used: number | null; limit: number | null }) {
  const size = 20;
  const stroke = 2.4;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = used != null && limit ? Math.min(1, used / limit) : 0;
  const progressColor = pct > 0.8 ? "var(--accent)" : "var(--glaze)";
  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      aria-hidden
    >
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

/** 输入条右侧的会话统计环：点击弹出容量/分项/命中率面板。 */
export function ContextStatsButton({ conversationId }: Props) {
  const [open, setOpen] = useState(false);
  const [stats, setStats] = useState<ContextStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [peekKey, setPeekKey] = useState<string | null>(null);
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
    // 环上的百分比需要数据：挂载即拉一次
    void load();
  }, [load]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  if (!conversationId) return null;

  const used = stats?.context.used_tokens ?? null;
  const limit = stats?.context.limit_tokens ?? null;
  const pct = used != null && limit ? (used / limit) * 100 : null;
  // 无上限时按构成占比铺满整条；比例始终以分项 tokens 为准
  const barDenominator = limit ?? used;
  const barSegments = (stats?.segments ?? []).filter(
    (seg) => seg.tokens > 0 && barDenominator,
  );

  return (
    <>
      <button
        ref={anchorRef}
        type="button"
        className="composer-icon-btn ctxstats-ring-btn"
        onClick={() => setOpen((v) => !v)}
        title={
          pct != null
            ? `会话统计：上下文 ${pct.toFixed(1)}%`
            : "会话统计"
        }
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
        onDismiss={() => {
          setOpen(false);
          setPeekKey(null);
        }}
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
            </div>
            <div className="ctxstats-bar-track">
              {barSegments.map((seg) => {
                const width =
                  barDenominator && barDenominator > 0
                    ? (seg.tokens / barDenominator) * 100
                    : 0;
                const share =
                  used && used > 0
                    ? ` · ${((seg.tokens / used) * 100).toFixed(1)}%`
                    : "";
                return (
                  <div
                    key={seg.key}
                    className="ctxstats-bar-seg"
                    style={{
                      width: `${width}%`,
                      background: segmentColor(seg.key),
                    }}
                    title={`${seg.label}${share}`}
                  />
                );
              })}
            </div>
            <div className="ctxstats-used">
              {used != null
                ? `${compactTokenCount(used)}${limit ? ` / ${compactTokenCount(limit)}` : ""} tokens`
                : "暂无用量的模型调用"}
            </div>
            <div className="ctxstats-section">
              {stats.segments.map((seg) => (
                <SegmentRow
                  key={seg.key}
                  seg={seg}
                  used={used}
                  peeked={peekKey === seg.key}
                  onTogglePeek={() =>
                    setPeekKey((k) => (k === seg.key ? null : seg.key))
                  }
                />
              ))}
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
            <div className="ctxstats-footnote">
              分项按实际注入文本估算；圆环为上次调用实测。点「记忆」可看注入正文。
            </div>
          </>
        ) : null}
      </FixedOverflowMenu>
    </>
  );
}

function SegmentRow({
  seg,
  used,
  peeked,
  onTogglePeek,
}: {
  seg: ContextStatsSegment;
  used: number | null;
  peeked: boolean;
  onTogglePeek: () => void;
}) {
  const segPct =
    used != null && used > 0 ? (seg.tokens / used) * 100 : null;
  const canPeek = seg.key === "memory";
  const preview = (seg.preview || "").trim();
  return (
    <div>
      {canPeek ? (
        <button
          type="button"
          className="ctxstats-row ctxstats-row--peek"
          onClick={onTogglePeek}
          aria-expanded={peeked}
          title={peeked ? "收起记忆正文" : "查看注入的记忆正文"}
        >
          <span className="ctxstats-row-label">
            <span
              className="ctxstats-dot"
              style={{ background: segmentColor(seg.key) }}
            />
            {seg.label}
          </span>
          <span className="ctxstats-row-value">
            {compactTokenCount(seg.tokens)}
            {segPct != null ? ` · ${segPct.toFixed(1)}%` : ""}
          </span>
        </button>
      ) : (
        <div className="ctxstats-row">
          <span className="ctxstats-row-label">
            <span
              className="ctxstats-dot"
              style={{ background: segmentColor(seg.key) }}
            />
            {seg.label}
          </span>
          <span className="ctxstats-row-value">
            {compactTokenCount(seg.tokens)}
            {segPct != null ? ` · ${segPct.toFixed(1)}%` : ""}
          </span>
        </div>
      )}
      {canPeek && peeked ? (
        <pre className="ctxstats-preview">
          {preview || "本轮未注入记忆"}
        </pre>
      ) : null}
    </div>
  );
}
