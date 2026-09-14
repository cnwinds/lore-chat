import { useEffect, useState } from "react";
import type { ChatMessage } from "../../types/chat";
import {
  getChannelLogs,
  getChannelTimeline,
  getChannelUsage,
  type ChannelInstance,
  type ChannelLogItem,
} from "../../api/channelPlugins";
import { formatOpenApiWhen } from "../settings/openApiSettingsModel";
import { accessGuide, revokeTabLabel, type DetailTab } from "./channelUiModel";

type TranscriptSeg = { title: string; messages: ChatMessage[] };

type Props = {
  inst: ChannelInstance;
  busy: boolean;
  onRevoke: (id: string) => void;
};

export function ChannelDetails({ inst, busy, onRevoke }: Props) {
  const [tab, setTab] = useState<DetailTab>("guide");
  const [transcript, setTranscript] = useState<TranscriptSeg[] | null>(null);
  const [logs, setLogs] = useState<ChannelLogItem[] | null>(null);
  const [usage, setUsage] = useState<{
    calls?: number;
    total_tokens?: number;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setTab("guide");
    setTranscript(null);
    setLogs(null);
    setUsage(null);
    setError(null);
  }, [inst.id]);

  useEffect(() => {
    if (tab !== "sessions" && tab !== "logs") return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    const run =
      tab === "sessions"
        ? async () => {
            if (!inst.role_id) {
              setTranscript([]);
              return;
            }
            const tl = await getChannelTimeline(inst.role_id);
            if (cancelled) return;
            setTranscript(
              (tl.segments || []).map((seg) => ({
                title: seg.title || "会话",
                messages: (seg.messages || []) as ChatMessage[],
              })),
            );
          }
        : async () => {
            const [logRes, usageRes] = await Promise.all([
              getChannelLogs(inst.id),
              getChannelUsage(inst.id).catch(() => null),
            ]);
            if (cancelled) return;
            setLogs(logRes.items || []);
            setUsage(usageRes?.totals || null);
          };
    void run()
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tab, inst.id, inst.role_id]);

  const guide = accessGuide(inst.type_id);
  const revokeLabel = revokeTabLabel(inst.type_id);
  const tabs: { id: DetailTab; label: string }[] = [
    { id: "guide", label: "接入说明" },
    { id: "sessions", label: "会话" },
    { id: "logs", label: "日志" },
    { id: "revoke", label: revokeLabel },
  ];

  return (
    <div className="channel-details">
      <div className="channel-seg" role="tablist" aria-label={`${inst.name} 详情`}>
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            className={`channel-seg-btn${tab === item.id ? " channel-seg-btn--active" : ""}`}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {error ? <p className="settings-panel-error">{error}</p> : null}

      {tab === "guide" ? (
        <div className="channel-details-body">
          <p className="channel-guide-lead">{guide.lead}</p>
          <ol className="channel-guide-steps">
            {guide.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          {inst.config?.callback_url ||
          inst.config?.request_url ||
          inst.config?.webhook_url ? (
            <p className="openapi-card-meta">
              回调：
              <code>
                {inst.config.callback_url ||
                  inst.config.request_url ||
                  inst.config.webhook_url}
              </code>
            </p>
          ) : null}
          {guide.curl ? <pre className="openapi-curl">{guide.curl}</pre> : null}
        </div>
      ) : null}

      {tab === "sessions" ? (
        <div className="channel-details-body">
          {loading && transcript == null ? (
            <p className="channel-panel-muted">加载会话…</p>
          ) : transcript && transcript.length === 0 ? (
            <p className="channel-panel-muted">还没有调用。消息进来之后会出现在这里。</p>
          ) : (
            <div className="openapi-logs">
              {(transcript || []).map((seg, i) => (
                <section key={`${seg.title}-${i}`} className="openapi-log-seg">
                  <h4>{seg.title}</h4>
                  {seg.messages.map((m) => (
                    <article
                      key={m.id || `${seg.title}-${m.role}-${m.ts}`}
                      className={`openapi-msg openapi-msg--${m.role}`}
                    >
                      <span>{m.role === "user" ? "调用" : "回复"}</span>
                      <p>{m.text?.trim() || "（无正文）"}</p>
                    </article>
                  ))}
                </section>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {tab === "logs" ? (
        <div className="channel-details-body">
          {loading && logs == null ? (
            <p className="channel-panel-muted">加载日志…</p>
          ) : (
            <>
              {usage ? (
                <p className="openapi-card-meta">
                  调用 {usage.calls ?? 0} 次
                  {usage.total_tokens != null ? ` · ${usage.total_tokens} tokens` : ""}
                </p>
              ) : null}
              {logs && logs.length === 0 ? (
                <p className="channel-panel-muted">
                  还没有日志。连接、入站失败和出站重试会出现在这里。
                </p>
              ) : (
                <ul className="openapi-instance-logs">
                  {(logs || []).map((item) => (
                    <li
                      key={item.id}
                      className={`openapi-instance-log openapi-instance-log--${item.level}`}
                    >
                      <span>{formatOpenApiWhen(item.ts)}</span>
                      <strong>{item.kind}</strong>
                      <p>{item.message}</p>
                      {item.duration_ms != null ? <em>{item.duration_ms} ms</em> : null}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      ) : null}

      {tab === "revoke" ? (
        <div className="channel-details-body">
          <p className="channel-guide-lead">
            {inst.type_id === "script_api"
              ? "吊销后外部将无法再用这把 Key。历史仍可查看。"
              : "停用后外部将无法再发来消息。历史仍可查看。"}
          </p>
          <button
            type="button"
            className="openapi-btn openapi-btn--danger"
            disabled={busy || !inst.enabled}
            onClick={() => onRevoke(inst.id)}
          >
            {inst.enabled ? revokeLabel : "已停用"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
