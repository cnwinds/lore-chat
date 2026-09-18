import { useState } from "react";

type Props = {
  /** danger=红（已禁用），warn=琥珀（冷却中） */
  tone: "danger" | "warn";
  /** 一行摘要（如「已禁用 · Error code: 404 - …」，过长自动省略） */
  summary: string;
  /** 完整错误原因；可展开查看 */
  detail?: string | null;
  retryLabel?: string;
  retryDisabled?: boolean;
  onRetry?: () => void;
};

/** 模型/供应商健康状态条：一行摘要 + 可展开的完整错误 + 重试动作。 */
export function SettingsHealthBar({
  tone,
  summary,
  detail,
  retryLabel = "立即重试",
  retryDisabled,
  onRetry,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const hasDetail = Boolean(detail && detail.trim());

  return (
    <div className={`settings-health-bar settings-health-bar--${tone}`}>
      <span className="settings-health-dot" aria-hidden />
      <span className="settings-health-text" title={summary}>
        {summary}
      </span>
      {hasDetail ? (
        <button
          type="button"
          className="settings-health-detail-btn"
          aria-expanded={expanded}
          title="查看完整错误"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "收起" : "详情"}
        </button>
      ) : null}
      {onRetry ? (
        <button
          type="button"
          className="settings-btn settings-btn--compact settings-btn--secondary"
          disabled={retryDisabled}
          onClick={onRetry}
        >
          {retryLabel}
        </button>
      ) : null}
      {expanded && hasDetail ? (
        <div className="settings-health-detail" role="status">
          {detail}
        </div>
      ) : null}
    </div>
  );
}
