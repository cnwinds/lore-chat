import type { BgNode, BgPurposeStats } from "../../types/background";
import { formatBackgroundRelativeTime } from "./backgroundUtils";

function TriggerIcon({ kind }: { kind: BgNode["trigger_kind"] }) {
  if (kind === "schedule") {
    return (
      <svg className="bgflow-node-icon" viewBox="0 0 24 24" aria-hidden>
        <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.5" />
        <path d="M12 7v5l3 2" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    );
  }
  if (kind === "event") {
    return (
      <svg className="bgflow-node-icon" viewBox="0 0 24 24" aria-hidden>
        <path
          d="M13 2L4 14h7l-1 8 9-12h-7l1-8z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  return (
    <svg className="bgflow-node-icon" viewBox="0 0 24 24" aria-hidden>
      <path
        d="M9 11V8a3 3 0 1 1 6 0v3M6 11h12v8a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2v-8z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function StoreIcon() {
  return (
    <svg className="bgflow-node-icon" viewBox="0 0 24 24" aria-hidden>
      <ellipse cx="12" cy="6" rx="7" ry="2.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path
        d="M5 6v10c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <path
        d="M5 11c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
      />
    </svg>
  );
}

function GuardIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" aria-hidden>
      <path
        d="M12 3 4 6v6c0 5 3.5 8.5 8 9 4.5-.5 8-4 8-9V6l-8-3z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
      />
    </svg>
  );
}

type Props = {
  node: BgNode;
  stats: BgPurposeStats | null;
  nodePaused: boolean;
  selected: boolean;
  linkTargetTitle: (laneId: string) => string;
  onSelect: () => void;
  onLinkClick: (laneId: string) => void;
};

export function FlowNode({
  node,
  stats,
  nodePaused,
  selected,
  linkTargetTitle,
  onSelect,
  onLinkClick,
}: Props) {
  const chainClass =
    node.chain === "utility"
      ? "bgflow-node--chain-utility"
      : node.chain === "chat"
        ? "bgflow-node--chain-chat"
        : node.chain === "embed"
          ? "bgflow-node--chain-embed"
          : "";

  const typeClass =
    node.type === "trigger"
      ? "bgflow-node--trigger"
      : node.type === "code"
        ? "bgflow-node--code"
        : node.type === "store"
          ? "bgflow-node--store"
          : "";

  const footParts: string[] = [];
  if (stats && stats.calls_24h > 0) {
    footParts.push(`24h ${stats.calls_24h} 次`);
    if (stats.last_call_at) {
      footParts.push(formatBackgroundRelativeTime(stats.last_call_at));
    }
  } else if (node.purpose) {
    footParts.push("尚无调用");
  }

  let nodeIcon = null;
  if (node.type === "trigger") nodeIcon = <TriggerIcon kind={node.trigger_kind} />;
  if (node.type === "store") nodeIcon = <StoreIcon />;

  return (
    <div className="bgflow-node-wrap">
      <button
        type="button"
        className={`bgflow-node ${typeClass} ${chainClass}${selected ? " bgflow-node--selected" : ""}${nodePaused ? " bgflow-node--paused" : ""}`}
        onClick={onSelect}
        aria-pressed={selected}
      >
        {nodePaused ? <span className="bgflow-node-paused-badge">已暂停</span> : null}
        <div className="bgflow-node-head">
          {nodeIcon}
          <div>
            <p className="bgflow-node-title">{node.title}</p>
            {node.subtitle ? <p className="bgflow-node-sub">{node.subtitle}</p> : null}
            {node.type === "turn" ? (
              <span className="bgflow-node-type-tag">走主对话提示词</span>
            ) : null}
            {node.type === "code" ? (
              <span className="bgflow-node-type-tag">无模型</span>
            ) : null}
          </div>
        </div>
        {(footParts.length > 0 || stats?.errors_24h || node.guards.length > 0) && (
          <div className="bgflow-node-foot">
            {footParts.join(" · ")}
            {stats && stats.errors_24h > 0 ? (
              <span className="bgflow-error-dot" title="24 小时内有失败" aria-label="有失败" />
            ) : null}
            {stats?.last_status === "error" ? (
              <span className="bgflow-error-dot" title="最近一次失败" aria-label="最近失败" />
            ) : null}
            {node.guards.length > 0 ? (
              <span className="bgflow-node-guard-badge" title="代码兜底">
                <GuardIcon />
                {node.guards.length}
              </span>
            ) : null}
          </div>
        )}
      </button>
      {node.links.length > 0 ? (
        <div className="bgflow-node-links">
          {node.links.map((link) => (
            <button
              key={`${link.lane}-${link.label}`}
              type="button"
              className="bgflow-link-chip"
              onClick={(e) => {
                e.stopPropagation();
                onLinkClick(link.lane);
              }}
            >
              → {linkTargetTitle(link.lane)}：{link.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
