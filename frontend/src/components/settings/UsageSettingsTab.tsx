import { useCallback, useEffect, useMemo, useState } from "react";
import {
  clearUsage,
  getUsageEvents,
  getUsagePrefs,
  getUsagePrices,
  getUsageSummary,
  putUsagePrefs,
  putUsagePrice,
  type UsageAgg,
  type UsageEvent,
  type UsagePrice,
  type UsageSummary,
} from "../../api";

type Granularity = "hour" | "day" | "week" | "month";

const GRANULARITY_OPTIONS: { value: Granularity; label: string }[] = [
  { value: "hour", label: "时" },
  { value: "day", label: "日" },
  { value: "week", label: "周" },
  { value: "month", label: "月" },
];

function fmtCost(n: number | null | undefined, known: boolean): string {
  if (!known || n == null) return "—";
  if (n < 0.01) return n.toFixed(6);
  if (n < 1) return n.toFixed(4);
  return n.toFixed(2);
}

function fmtInt(n: number): string {
  return n.toLocaleString("zh-CN");
}

function fmtRange(start: string, end: string): string {
  const a = start.slice(0, 10);
  const b = end.slice(0, 10);
  return a === b ? a : `${a} → ${b}`;
}

function fmtEventTime(ts: string): string {
  return (ts || "").replace("T", " ").slice(0, 16);
}

function kindLabel(kind: string): string {
  switch (kind) {
    case "chat":
      return "对话";
    case "embed":
      return "向量";
    case "completion":
      return "补全";
    default:
      return kind || "—";
  }
}

function bucketLabel(bucket: string | undefined, granularity: string): string {
  if (!bucket) return "—";
  if (granularity === "hour" && bucket.length >= 13) {
    return `${bucket.slice(5, 10)} ${bucket.slice(11, 13)}时`;
  }
  if (granularity === "day" && bucket.length >= 10) {
    return bucket.slice(5, 10);
  }
  if (granularity === "week") return bucket;
  if (granularity === "month" && bucket.length >= 7) return bucket.slice(0, 7);
  return bucket;
}

function priceKey(p: UsagePrice): string {
  return `${p.prompt_per_1m ?? ""}|${p.completion_per_1m ?? ""}|${p.cache_input_per_1m ?? ""}|${p.embed_per_1m ?? ""}`;
}

/** 按实际调用 kind（或模型名启发式）决定显示哪些价目字段。 */
function priceFieldVisibility(row: UsagePrice): {
  chat: boolean;
  embed: boolean;
} {
  const kinds = row.kinds ?? [];
  const hasEmbed = kinds.includes("embed");
  const hasChat = kinds.some((k) => k !== "embed");
  if (hasEmbed || hasChat) {
    return { chat: hasChat, embed: hasEmbed };
  }
  const embedLike = /embed/i.test(row.model);
  return { chat: !embedLike, embed: embedLike };
}

function MetricCard({
  label,
  value,
  hint,
  emphasize,
}: {
  label: string;
  value: string;
  hint?: string;
  emphasize?: boolean;
}) {
  return (
    <div className={`usage-metric${emphasize ? " usage-metric--accent" : ""}`}>
      <span className="usage-metric-label">{label}</span>
      <span className="usage-metric-value">{value}</span>
      {hint ? <span className="usage-metric-hint">{hint}</span> : null}
    </div>
  );
}

function TrendChart({
  buckets,
  granularity,
}: {
  buckets: UsageAgg[];
  granularity: string;
}) {
  const max = Math.max(1, ...buckets.map((b) => b.total_tokens || b.calls || 0));
  if (buckets.length === 0) {
    return <p className="usage-empty">当前区间暂无趋势数据</p>;
  }
  return (
    <div className="usage-trend" role="img" aria-label="用量趋势">
      {buckets.map((b) => {
        const height = Math.max(
          4,
          Math.round(((b.total_tokens || b.calls || 0) / max) * 100),
        );
        const title = `${bucketLabel(b.bucket, granularity)} · ${fmtInt(b.calls)} 次 · ${fmtInt(b.total_tokens)} tokens`;
        return (
          <div key={b.bucket ?? title} className="usage-trend-col" title={title}>
            <div className="usage-trend-bar-track">
              <div className="usage-trend-bar" style={{ height: `${height}%` }} />
            </div>
            <span className="usage-trend-label">
              {bucketLabel(b.bucket, granularity)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function ModelBreakdown({ rows }: { rows: Array<UsageAgg & { model: string }> }) {
  if (rows.length === 0) {
    return <p className="usage-empty">暂无模型用量</p>;
  }
  const maxTokens = Math.max(1, ...rows.map((r) => r.total_tokens));
  return (
    <ul className="usage-model-list">
      {rows.map((row) => {
        const pct = Math.round((row.total_tokens / maxTokens) * 100);
        const costKnown = row.cost_known_calls > 0;
        return (
          <li key={row.model} className="usage-model-row">
            <div className="usage-model-head">
              <span className="usage-model-name" title={row.model}>
                {row.model}
              </span>
              <span className="usage-model-cost">
                {fmtCost(row.cost, costKnown)}
              </span>
            </div>
            <div className="usage-model-bar-track" aria-hidden>
              <div className="usage-model-bar" style={{ width: `${pct}%` }} />
            </div>
            <div className="usage-model-meta">
              <span>{fmtInt(row.calls)} 次</span>
              <span>{fmtInt(row.prompt_tokens)} / {fmtInt(row.completion_tokens)}</span>
              {row.unpriced_calls > 0 ? (
                <span className="usage-warn">{row.unpriced_calls} 未定价</span>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function formatEventTokens(ev: UsageEvent): string {
  if (!ev.tokens_known) return "tokens 未知";
  if (ev.kind === "embed") {
    const n = ev.total_tokens ?? ev.prompt_tokens ?? 0;
    return `Embed ${fmtInt(n)}`;
  }
  const input = ev.prompt_tokens ?? 0;
  const output = ev.completion_tokens ?? 0;
  const cache = ev.cache_tokens ?? 0;
  if (cache > 0) {
    return `In ${fmtInt(input)} · Out ${fmtInt(output)} · Cache ${fmtInt(cache)}`;
  }
  return `In ${fmtInt(input)} · Out ${fmtInt(output)}`;
}

function EventList({ events }: { events: UsageEvent[] }) {
  if (events.length === 0) {
    return <p className="usage-empty">暂无调用记录</p>;
  }
  return (
    <ul className="usage-event-list">
      {events.map((ev) => {
        const ok = ev.status === "ok";
        return (
          <li key={ev.id} className="usage-event-row">
            <div className="usage-event-main">
              <span className="usage-event-time">{fmtEventTime(ev.ts)}</span>
              <span
                className={`usage-event-status${ok ? "" : " usage-event-status--err"}`}
              >
                {ok ? "成功" : "失败"}
              </span>
            </div>
            <div className="usage-event-detail">
              <span className="usage-event-model" title={ev.model}>
                {ev.model}
              </span>
              <span className="usage-event-kind">{kindLabel(ev.kind)}</span>
            </div>
            <div className="usage-event-nums">
              <span>{formatEventTokens(ev)}</span>
              <span>{fmtCost(ev.cost, ev.cost != null)}</span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function UsageSettingsTab() {
  const [granularity, setGranularity] = useState<Granularity>("day");
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [events, setEvents] = useState<UsageEvent[]>([]);
  const [eventsLoaded, setEventsLoaded] = useState(false);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [prices, setPrices] = useState<UsagePrice[]>([]);
  const [baselinePrices, setBaselinePrices] = useState<Record<string, string>>(
    {},
  );
  const [prefs, setPrefs] = useState<{
    timezone: string;
    retention_days: number;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingPrice, setSavingPrice] = useState<string | null>(null);
  const [eventsOpen, setEventsOpen] = useState(false);
  const [prefsOpen, setPrefsOpen] = useState(false);
  const [pricesOpen, setPricesOpen] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, p, pr] = await Promise.all([
        getUsageSummary({ granularity }),
        getUsagePrices(),
        getUsagePrefs(),
      ]);
      setSummary(s);
      setPrices(p.items);
      setBaselinePrices(
        Object.fromEntries(p.items.map((row) => [row.model, priceKey(row)])),
      );
      setPrefs(pr);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [granularity]);

  const loadEvents = useCallback(async () => {
    setEventsLoading(true);
    setError(null);
    try {
      const e = await getUsageEvents({ limit: 40 });
      setEvents(e.items);
      setEventsLoaded(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载调用记录失败");
    } finally {
      setEventsLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (!eventsOpen) return;
    void loadEvents();
  }, [eventsOpen, loadEvents]);

  const dirtyModels = useMemo(() => {
    const set = new Set<string>();
    for (const row of prices) {
      if (baselinePrices[row.model] !== priceKey(row)) set.add(row.model);
    }
    return set;
  }, [prices, baselinePrices]);

  async function savePrice(row: UsagePrice) {
    setSavingPrice(row.model);
    setError(null);
    try {
      const saved = await putUsagePrice({
        model: row.model,
        prompt_per_1m: row.prompt_per_1m,
        completion_per_1m: row.completion_per_1m,
        cache_input_per_1m: row.cache_input_per_1m,
        embed_per_1m: row.embed_per_1m,
      });
      setPrices((prev) =>
        prev.map((p) => (p.model === saved.model ? { ...p, ...saved } : p)),
      );
      setBaselinePrices((prev) => ({
        ...prev,
        [saved.model]: priceKey(saved),
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存价目失败");
    } finally {
      setSavingPrice(null);
    }
  }

  async function handleClear() {
    if (!window.confirm("确定清空全部用量记录？价目表会保留。")) return;
    try {
      await clearUsage();
      setEvents([]);
      setEventsLoaded(false);
      await reload();
      if (eventsOpen) await loadEvents();
    } catch (err) {
      setError(err instanceof Error ? err.message : "清空失败");
    }
  }

  async function handleRefresh() {
    await reload();
    if (eventsOpen) await loadEvents();
  }

  async function savePrefs(next: {
    timezone?: string;
    retention_days?: number;
  }) {
    try {
      const pr = await putUsagePrefs(next);
      setPrefs(pr);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存偏好失败");
    }
  }

  function updatePrice(
    model: string,
    field:
      | "prompt_per_1m"
      | "completion_per_1m"
      | "cache_input_per_1m"
      | "embed_per_1m",
    raw: string,
  ) {
    setPrices((prev) =>
      prev.map((p) =>
        p.model === model
          ? { ...p, [field]: raw === "" ? null : Number(raw) }
          : p,
      ),
    );
  }

  if (loading && !summary) {
    return <p className="settings-panel-hint">加载用量…</p>;
  }

  const totals = summary?.totals;
  const costKnown = (totals?.cost_known_calls ?? 0) > 0;
  const period =
    summary?.start && summary?.end
      ? fmtRange(summary.start, summary.end)
      : "本月";

  return (
    <div
      className="settings-tab-panel usage-panel"
      role="tabpanel"
      id="settings-panel-usage"
      aria-labelledby="settings-tab-usage"
    >
      {error ? <p className="settings-panel-error">{error}</p> : null}

      <section className="usage-section usage-section--hero">
        <div className="usage-hero-top">
          <div className="usage-hero-copy">
            <h3 className="usage-section-title">本月用量</h3>
            <p className="usage-section-sub">
              {period}
              <span className="usage-dot" aria-hidden>
                ·
              </span>
              {prefs?.timezone ?? "Asia/Shanghai"}
            </p>
          </div>
          <button
            type="button"
            className="settings-btn settings-btn--secondary settings-btn--compact"
            onClick={() => void handleRefresh()}
            disabled={loading || eventsLoading}
          >
            {loading || eventsLoading ? "刷新中" : "刷新"}
          </button>
        </div>

        {totals ? (
          <div className="usage-metrics">
            <MetricCard label="调用" value={fmtInt(totals.calls)} />
            <MetricCard
              label="Tokens"
              value={fmtInt(totals.total_tokens)}
              hint={
                totals.unknown_token_calls > 0
                  ? `${totals.unknown_token_calls} 笔未知`
                  : undefined
              }
            />
            <MetricCard
              label="费用"
              value={fmtCost(totals.cost, costKnown)}
              emphasize
              hint={
                totals.unpriced_calls > 0
                  ? `${totals.unpriced_calls} 笔未定价`
                  : undefined
              }
            />
          </div>
        ) : null}

        <div
          className="usage-segmented"
          role="radiogroup"
          aria-label="统计粒度"
        >
          {GRANULARITY_OPTIONS.map((opt) => {
            const active = granularity === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                role="radio"
                aria-checked={active}
                className={`usage-segment${active ? " usage-segment--active" : ""}`}
                onClick={() => setGranularity(opt.value)}
              >
                {opt.label}
              </button>
            );
          })}
        </div>

        <TrendChart
          buckets={summary?.by_bucket ?? []}
          granularity={granularity}
        />
      </section>

      <section className="usage-section">
        <h3 className="usage-section-title">按模型</h3>
        <p className="usage-section-sub">条长度表示相对 Token 占比</p>
        <ModelBreakdown rows={summary?.by_model ?? []} />
      </section>

      <section className="usage-section">
        <button
          type="button"
          className="usage-disclosure"
          aria-expanded={eventsOpen}
          onClick={() => setEventsOpen((v) => !v)}
        >
          <span className="usage-disclosure-copy">
            <span className="usage-section-title">最近调用</span>
            <span className="usage-section-sub">
              {eventsOpen
                ? eventsLoading
                  ? "加载中…"
                  : eventsLoaded
                    ? `最近 ${events.length} 条`
                    : "展开后加载"
                : "点击展开后加载"}
            </span>
          </span>
          <span className="usage-disclosure-chevron" aria-hidden>
            {eventsOpen ? "▾" : "▸"}
          </span>
        </button>
        {eventsOpen ? (
          eventsLoading && !eventsLoaded ? (
            <p className="usage-empty">加载调用记录…</p>
          ) : (
            <EventList events={events} />
          )
        ) : null}
      </section>

      <section className="usage-section">
        <button
          type="button"
          className="usage-disclosure"
          aria-expanded={pricesOpen}
          onClick={() => setPricesOpen((v) => !v)}
        >
          <span className="usage-disclosure-copy">
            <span className="usage-section-title">价目表</span>
            <span className="usage-section-sub">
              每百万 tokens · {prices.length} 个模型
              {dirtyModels.size > 0 ? ` · ${dirtyModels.size} 处未保存` : ""}
            </span>
          </span>
          <span className="usage-disclosure-chevron" aria-hidden>
            {pricesOpen ? "▾" : "▸"}
          </span>
        </button>
        {pricesOpen ? (
          <div className="usage-price-list">
            <p className="usage-section-sub usage-price-hint">
              单位：每百万 tokens。对话模型显示 Input / Output / Cache；向量模型只显示
              Embed。
            </p>
            {prices.length === 0 ? (
              <p className="usage-empty">见过的模型会自动出现在此</p>
            ) : (
              prices.map((row) => {
                const dirty = dirtyModels.has(row.model);
                const saving = savingPrice === row.model;
                const fields = priceFieldVisibility(row);
                return (
                  <div key={row.model} className="usage-price-card">
                    <div className="usage-price-card-head">
                      <div className="usage-price-card-title">
                        <span className="usage-model-name" title={row.model}>
                          {row.model}
                        </span>
                        <span className="usage-price-role">
                          {fields.chat && fields.embed
                            ? "对话 · 向量"
                            : fields.embed
                              ? "向量"
                              : "对话"}
                        </span>
                      </div>
                      <button
                        type="button"
                        className={`settings-btn settings-btn--compact${
                          dirty
                            ? " settings-btn--primary"
                            : " settings-btn--secondary"
                        }`}
                        disabled={!dirty || saving}
                        onClick={() => void savePrice(row)}
                      >
                        {saving ? "保存中" : dirty ? "保存" : "已保存"}
                      </button>
                    </div>

                    {fields.chat ? (
                      <div className="usage-price-group">
                        <div className="usage-price-fields">
                          <label className="usage-price-field">
                            <span>Input</span>
                            <input
                              type="number"
                              step="any"
                              inputMode="decimal"
                              aria-label={`${row.model} Input 每百万 tokens`}
                              placeholder="/ MTok"
                              value={row.prompt_per_1m ?? ""}
                              onChange={(e) =>
                                updatePrice(
                                  row.model,
                                  "prompt_per_1m",
                                  e.target.value,
                                )
                              }
                            />
                          </label>
                          <label className="usage-price-field">
                            <span>Output</span>
                            <input
                              type="number"
                              step="any"
                              inputMode="decimal"
                              aria-label={`${row.model} Output 每百万 tokens`}
                              placeholder="/ MTok"
                              value={row.completion_per_1m ?? ""}
                              onChange={(e) =>
                                updatePrice(
                                  row.model,
                                  "completion_per_1m",
                                  e.target.value,
                                )
                              }
                            />
                          </label>
                          <label className="usage-price-field usage-price-field--wide">
                            <span>Cache Input</span>
                            <input
                              type="number"
                              step="any"
                              inputMode="decimal"
                              aria-label={`${row.model} Cache Input 每百万 tokens`}
                              placeholder="/ MTok"
                              value={row.cache_input_per_1m ?? ""}
                              onChange={(e) =>
                                updatePrice(
                                  row.model,
                                  "cache_input_per_1m",
                                  e.target.value,
                                )
                              }
                            />
                          </label>
                        </div>
                      </div>
                    ) : null}

                    {fields.embed ? (
                      <div className="usage-price-group">
                        <div className="usage-price-fields">
                          <label className="usage-price-field usage-price-field--wide">
                            <span>Embed</span>
                            <input
                              type="number"
                              step="any"
                              inputMode="decimal"
                              aria-label={`${row.model} Embed 每百万 tokens`}
                              placeholder="/ MTok"
                              value={row.embed_per_1m ?? ""}
                              onChange={(e) =>
                                updatePrice(
                                  row.model,
                                  "embed_per_1m",
                                  e.target.value,
                                )
                              }
                            />
                          </label>
                        </div>
                      </div>
                    ) : null}
                  </div>
                );
              })
            )}
          </div>
        ) : null}
      </section>

      <section className="usage-section">
        <button
          type="button"
          className="usage-disclosure"
          aria-expanded={prefsOpen}
          onClick={() => setPrefsOpen((v) => !v)}
        >
          <span className="usage-disclosure-copy">
            <span className="usage-section-title">数据与偏好</span>
            <span className="usage-section-sub">
              保留 {prefs?.retention_days ?? 365} 天
            </span>
          </span>
          <span className="usage-disclosure-chevron" aria-hidden>
            {prefsOpen ? "▾" : "▸"}
          </span>
        </button>
        {prefsOpen ? (
          <div className="usage-prefs">
            <label className="settings-field">
              <span>统计时区</span>
              <input
                value={prefs?.timezone ?? "Asia/Shanghai"}
                onChange={(e) =>
                  setPrefs((p) =>
                    p ? { ...p, timezone: e.target.value } : p,
                  )
                }
                onBlur={(e) => void savePrefs({ timezone: e.target.value })}
              />
            </label>
            <label className="settings-field">
              <span>保留天数</span>
              <input
                type="number"
                min={1}
                value={prefs?.retention_days ?? 365}
                onChange={(e) =>
                  setPrefs((p) =>
                    p
                      ? {
                          ...p,
                          retention_days: Number(e.target.value) || 365,
                        }
                      : p,
                  )
                }
                onBlur={(e) =>
                  void savePrefs({
                    retention_days: Number(e.target.value) || 365,
                  })
                }
              />
            </label>
            <div className="usage-danger">
              <div className="usage-danger-copy">
                <span className="usage-danger-title">清空用量记录</span>
                <span className="usage-danger-desc">
                  删除全部调用明细与汇总；价目表保留
                </span>
              </div>
              <button
                type="button"
                className="settings-btn settings-btn--compact usage-danger-btn"
                onClick={() => void handleClear()}
              >
                清空
              </button>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
