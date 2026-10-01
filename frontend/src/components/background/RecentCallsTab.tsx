import { useCallback, useEffect, useState } from "react";
import { getBackgroundCall, listBackgroundCalls } from "../../api";
import type { BgCallDetail, BgCallSummary } from "../../types/background";
import { CopyButton } from "../CopyButton";
import { formatBackgroundRelativeTime } from "./backgroundUtils";

type Props = {
  purpose: string;
};

function CallMessage({ role, content }: { role: string; content: string }) {
  const [expanded, setExpanded] = useState(false);
  const long = content.length > 320;
  return (
    <div className="bgflow-call-msg">
      <div className="bgflow-call-msg-role">
        {role} · <CopyButton text={content} />
      </div>
      <div
        className={`bgflow-call-msg-body${long && !expanded ? " bgflow-call-msg-body--collapsed" : ""}`}
      >
        {content}
      </div>
      {long ? (
        <button
          type="button"
          className="bgflow-settings-link"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "收起" : "展开全文"}
        </button>
      ) : null}
    </div>
  );
}

export function RecentCallsTab({ purpose }: Props) {
  const [calls, setCalls] = useState<BgCallSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<number, BgCallDetail>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { calls: list } = await listBackgroundCalls(purpose, 20);
      setCalls(list);
    } catch {
      setError("加载失败");
    } finally {
      setLoading(false);
    }
  }, [purpose]);

  useEffect(() => {
    void load();
  }, [load]);

  const loadDetail = async (id: number) => {
    if (details[id]) return;
    try {
      const d = await getBackgroundCall(id);
      setDetails((prev) => ({ ...prev, [id]: d }));
    } catch {
      /* ignore */
    }
  };

  if (loading) return <p className="bgflow-empty">加载中…</p>;
  if (error) {
    return (
      <div className="bgflow-error">
        {error}
        <div>
          <button type="button" className="bgflow-retry-btn" onClick={() => void load()}>
            重试
          </button>
        </div>
      </div>
    );
  }
  if (calls.length === 0) {
    return <p className="bgflow-empty">上线后首次调用才会有记录</p>;
  }

  return (
    <div className="bgflow-calls-list">
      {calls.map((c) => {
        const detail = details[c.id];
        return (
          <details
            key={c.id}
            className="bgflow-call-row"
            onToggle={(e) => {
              if ((e.target as HTMLDetailsElement).open) void loadDetail(c.id);
            }}
          >
            <summary>
              <span>{formatBackgroundRelativeTime(c.ts)}</span>
              {c.variant ? <span>{c.variant}</span> : null}
              <span>{c.model_label ?? c.model ?? "—"}</span>
              {c.duration_ms != null ? <span>{c.duration_ms} ms</span> : null}
              {c.prompt_tokens != null ? (
                <span>
                  {c.prompt_tokens}/{c.completion_tokens ?? 0} tokens
                </span>
              ) : null}
              <span>{c.status === "ok" ? "成功" : "失败"}</span>
            </summary>
            <div className="bgflow-call-detail">
              {detail ? (
                <>
                  {detail.messages.map((m, i) => (
                    <CallMessage key={i} role={m.role} content={m.content} />
                  ))}
                  {detail.response != null ? (
                    <div className="bgflow-call-msg">
                      <div className="bgflow-call-msg-role">
                        模型返回
                        {detail.response_truncated ? "（已截断）" : ""} ·{" "}
                        <CopyButton text={detail.response} />
                      </div>
                      <div className="bgflow-call-msg-body">{detail.response}</div>
                    </div>
                  ) : null}
                  {detail.error ? (
                    <p className="bgflow-config-hint">{detail.error}</p>
                  ) : null}
                </>
              ) : (
                <p className="bgflow-empty">加载详情…</p>
              )}
            </div>
          </details>
        );
      })}
    </div>
  );
}
