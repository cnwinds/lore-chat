import { useCallback, useEffect, useState } from "react";
import {
  clearUsage,
  getUsageEvents,
  getUsagePrefs,
  getUsagePrices,
  getUsageSummary,
  putUsagePrefs,
  putUsagePrice,
  type UsageEvent,
  type UsagePrice,
  type UsageSummary,
} from "../../api";

type Granularity = "hour" | "day" | "week" | "month";

function fmtCost(n: number | null | undefined, known: boolean): string {
  if (!known || n == null) return "—";
  if (n < 0.01) return n.toFixed(6);
  return n.toFixed(4);
}

export function UsageSettingsTab() {
  const [granularity, setGranularity] = useState<Granularity>("day");
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [events, setEvents] = useState<UsageEvent[]>([]);
  const [prices, setPrices] = useState<UsagePrice[]>([]);
  const [prefs, setPrefs] = useState<{ timezone: string; retention_days: number } | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingPrice, setSavingPrice] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, e, p, pr] = await Promise.all([
        getUsageSummary({ granularity }),
        getUsageEvents({ limit: 40 }),
        getUsagePrices(),
        getUsagePrefs(),
      ]);
      setSummary(s);
      setEvents(e.items);
      setPrices(p.items);
      setPrefs(pr);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [granularity]);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function savePrice(row: UsagePrice) {
    setSavingPrice(row.model);
    setError(null);
    try {
      await putUsagePrice({
        model: row.model,
        prompt_per_1k: row.prompt_per_1k,
        completion_per_1k: row.completion_per_1k,
        embed_per_1k: row.embed_per_1k,
      });
      await reload();
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
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "清空失败");
    }
  }

  async function savePrefs(next: { timezone?: string; retention_days?: number }) {
    try {
      const pr = await putUsagePrefs(next);
      setPrefs(pr);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存偏好失败");
    }
  }

  if (loading && !summary) {
    return <p className="settings-panel-hint">加载用量…</p>;
  }

  const totals = summary?.totals;
  const costKnown = (totals?.cost_known_calls ?? 0) > 0;

  return (
    <div
      className="settings-tab-panel"
      role="tabpanel"
      id="settings-panel-usage"
      aria-labelledby="settings-tab-usage"
    >
      {error ? <p className="settings-panel-error">{error}</p> : null}

      <div className="settings-group">
        <h3 className="settings-group-title">汇总</h3>
        <p className="settings-group-hint">
          时区 {prefs?.timezone ?? "Asia/Shanghai"} · 默认本月 · 保留{" "}
          {prefs?.retention_days ?? 365} 天
        </p>
        <div className="settings-usage-toolbar">
          <label className="settings-field settings-usage-granularity">
            <span>粒度</span>
            <select
              value={granularity}
              onChange={(e) => setGranularity(e.target.value as Granularity)}
            >
              <option value="hour">按小时</option>
              <option value="day">按天</option>
              <option value="week">按周</option>
              <option value="month">按月</option>
            </select>
          </label>
          <button type="button" className="settings-btn" onClick={() => void reload()}>
            刷新
          </button>
          <button type="button" className="settings-btn" onClick={() => void handleClear()}>
            清空记录
          </button>
        </div>
        {totals ? (
          <div className="settings-usage-totals">
            <div>
              <span className="settings-usage-metric-label">调用</span>
              <strong>{totals.calls}</strong>
            </div>
            <div>
              <span className="settings-usage-metric-label">Tokens</span>
              <strong>{totals.total_tokens}</strong>
              {totals.unknown_token_calls > 0 ? (
                <span className="settings-group-hint">
                  （{totals.unknown_token_calls} 笔未知）
                </span>
              ) : null}
            </div>
            <div>
              <span className="settings-usage-metric-label">费用</span>
              <strong>{fmtCost(totals.cost, costKnown)}</strong>
              {totals.unpriced_calls > 0 ? (
                <span className="settings-group-hint">
                  （{totals.unpriced_calls} 笔未定价）
                </span>
              ) : null}
            </div>
          </div>
        ) : null}

        <div className="settings-usage-table-wrap">
          <table className="settings-usage-table">
            <thead>
              <tr>
                <th>模型</th>
                <th>调用</th>
                <th>Prompt</th>
                <th>Completion</th>
                <th>费用</th>
              </tr>
            </thead>
            <tbody>
              {(summary?.by_model ?? []).length === 0 ? (
                <tr>
                  <td colSpan={5}>暂无用量</td>
                </tr>
              ) : (
                summary!.by_model.map((row) => (
                  <tr key={row.model}>
                    <td>{row.model}</td>
                    <td>{row.calls}</td>
                    <td>{row.prompt_tokens}</td>
                    <td>{row.completion_tokens}</td>
                    <td>
                      {fmtCost(row.cost, row.cost_known_calls > 0)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="settings-group">
        <h3 className="settings-group-title">价目表</h3>
        <p className="settings-group-hint">
          单位：每 1K tokens 单价（记账时快照）。见过的模型会自动出现。
        </p>
        <div className="settings-usage-table-wrap">
          <table className="settings-usage-table">
            <thead>
              <tr>
                <th>模型</th>
                <th>Prompt /1K</th>
                <th>Completion /1K</th>
                <th>Embed /1K</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {prices.length === 0 ? (
                <tr>
                  <td colSpan={5}>尚无模型价目</td>
                </tr>
              ) : (
                prices.map((row, idx) => (
                  <tr key={row.model}>
                    <td>{row.model}</td>
                    <td>
                      <input
                        className="settings-usage-price-input"
                        type="number"
                        step="any"
                        value={row.prompt_per_1k ?? ""}
                        onChange={(e) => {
                          const v = e.target.value;
                          setPrices((prev) =>
                            prev.map((p, i) =>
                              i === idx
                                ? {
                                    ...p,
                                    prompt_per_1k: v === "" ? null : Number(v),
                                  }
                                : p,
                            ),
                          );
                        }}
                      />
                    </td>
                    <td>
                      <input
                        className="settings-usage-price-input"
                        type="number"
                        step="any"
                        value={row.completion_per_1k ?? ""}
                        onChange={(e) => {
                          const v = e.target.value;
                          setPrices((prev) =>
                            prev.map((p, i) =>
                              i === idx
                                ? {
                                    ...p,
                                    completion_per_1k: v === "" ? null : Number(v),
                                  }
                                : p,
                            ),
                          );
                        }}
                      />
                    </td>
                    <td>
                      <input
                        className="settings-usage-price-input"
                        type="number"
                        step="any"
                        value={row.embed_per_1k ?? ""}
                        onChange={(e) => {
                          const v = e.target.value;
                          setPrices((prev) =>
                            prev.map((p, i) =>
                              i === idx
                                ? {
                                    ...p,
                                    embed_per_1k: v === "" ? null : Number(v),
                                  }
                                : p,
                            ),
                          );
                        }}
                      />
                    </td>
                    <td>
                      <button
                        type="button"
                        className="settings-btn"
                        disabled={savingPrice === row.model}
                        onClick={() => void savePrice(row)}
                      >
                        保存
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="settings-group">
        <h3 className="settings-group-title">最近调用</h3>
        <div className="settings-usage-table-wrap">
          <table className="settings-usage-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>模型</th>
                <th>类型</th>
                <th>Tokens</th>
                <th>费用</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              {events.length === 0 ? (
                <tr>
                  <td colSpan={6}>暂无记录</td>
                </tr>
              ) : (
                events.map((ev) => (
                  <tr key={ev.id}>
                    <td>{(ev.ts || "").replace("T", " ").slice(0, 19)}</td>
                    <td>{ev.model}</td>
                    <td>{ev.kind}</td>
                    <td>
                      {ev.tokens_known
                        ? `${ev.prompt_tokens ?? 0}/${ev.completion_tokens ?? 0}`
                        : "未知"}
                    </td>
                    <td>{fmtCost(ev.cost, ev.cost != null)}</td>
                    <td>{ev.status === "ok" ? "成功" : "失败"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="settings-group">
        <h3 className="settings-group-title">偏好</h3>
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
                  ? { ...p, retention_days: Number(e.target.value) || 365 }
                  : p,
              )
            }
            onBlur={(e) =>
              void savePrefs({ retention_days: Number(e.target.value) || 365 })
            }
          />
        </label>
      </div>
    </div>
  );
}
