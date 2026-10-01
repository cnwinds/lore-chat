import { useEffect, useRef } from "react";
import type {
  BgLane,
  BgNode,
  BgPausable,
  BgStatus,
  BgWorkerStatus,
} from "../../types/background";
import {
  collectLanePauseKeys,
  formatBackgroundRelativeTime,
  pauseKeyLabel,
} from "./backgroundUtils";
import { FlowNode } from "./FlowNode";

function StepArrow() {
  return (
    <div className="bgflow-step-arrow" aria-hidden>
      <svg width="20" height="20" viewBox="0 0 24 24">
        <path
          d="M5 12h14m-4-4 4 4-4 4"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

type Props = {
  lane: BgLane;
  nodes: Record<string, BgNode>;
  status: BgStatus;
  pausable: BgPausable[];
  stacked: boolean;
  highlighted: boolean;
  selectedNodeId: string | null;
  pauseBusy: boolean;
  onSelectNode: (id: string) => void;
  onLinkClick: (laneId: string) => void;
  onPauseChange: (pauseKey: string, paused: boolean) => void;
  laneTitleById: (id: string) => string;
};

export function FlowLane({
  lane,
  nodes,
  status,
  pausable,
  stacked,
  highlighted,
  selectedNodeId,
  pauseBusy,
  onSelectNode,
  onLinkClick,
  onPauseChange,
  laneTitleById,
}: Props) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!highlighted || !ref.current) return;
    ref.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [highlighted]);

  const worker: BgWorkerStatus | null = lane.worker
    ? status.workers[lane.worker] ?? null
    : null;
  const lanePaused =
    lane.pause_key != null && status.paused.includes(lane.pause_key);
  const pauseKeys = collectLanePauseKeys(lane, nodes);

  return (
    <article
      ref={ref}
      className={`bgflow-lane${lanePaused ? " bgflow-lane--paused" : ""}${highlighted ? " bgflow-lane--highlight" : ""}`}
      data-lane-id={lane.id}
    >
      <div className="bgflow-lane-head">
        <div className="bgflow-lane-title-row">
          <h4 className="bgflow-lane-title">{lane.title}</h4>
          {lanePaused ? <span className="bgflow-lane-badge">已暂停</span> : null}
        </div>
        <p className="bgflow-lane-cadence">{lane.cadence}</p>
        {worker ? (
          <div className="bgflow-lane-worker">
            {worker.last_error ? <span className="bgflow-error-dot" aria-hidden /> : null}
            <span>
              {worker.label} · 上次{" "}
              {formatBackgroundRelativeTime(worker.last_run_at ?? worker.last_active_at)}
            </span>
          </div>
        ) : null}
        {pauseKeys.length > 0 ? (
          <div className="bgflow-lane-pause-list">
            {pauseKeys.map((key) => {
              const label = pauseKeyLabel(pausable, key);
              const checked = status.paused.includes(key);
              return (
                <label key={key} className="bgflow-pause-toggle">
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={pauseBusy}
                    aria-label={`暂停 ${label}`}
                    onChange={(e) => onPauseChange(key, e.target.checked)}
                  />
                  暂停 {label}
                </label>
              );
            })}
          </div>
        ) : null}
      </div>
      <div className={`bgflow-lane-flow${stacked ? " bgflow-lane-flow--stacked" : ""}`}>
        {lane.steps.map((step, stepIdx) => (
          <div key={`${lane.id}-step-${stepIdx}`} style={{ display: "contents" }}>
            {stepIdx > 0 ? <StepArrow /> : null}
            <div className={`bgflow-step${stacked ? " bgflow-step--stacked" : ""}`}>
              {step.nodes.length > 1 ? (
                <div className="bgflow-step-bracket">
                  {step.nodes.map((nodeId) => {
                    const node = nodes[nodeId];
                    if (!node) return null;
                    const nodePaused =
                      node.pause_key != null &&
                      status.paused.includes(node.pause_key);
                    return (
                      <FlowNode
                        key={nodeId}
                        node={node}
                        stats={node.purpose ? status.stats[node.purpose] ?? null : null}
                        nodePaused={nodePaused}
                        selected={selectedNodeId === nodeId}
                        linkTargetTitle={laneTitleById}
                        onSelect={() => onSelectNode(nodeId)}
                        onLinkClick={onLinkClick}
                      />
                    );
                  })}
                </div>
              ) : (
                <div className="bgflow-step-nodes">
                  {step.nodes.map((nodeId) => {
                    const node = nodes[nodeId];
                    if (!node) return null;
                    const nodePaused =
                      node.pause_key != null &&
                      status.paused.includes(node.pause_key);
                    return (
                      <FlowNode
                        key={nodeId}
                        node={node}
                        stats={node.purpose ? status.stats[node.purpose] ?? null : null}
                        nodePaused={nodePaused}
                        selected={selectedNodeId === nodeId}
                        linkTargetTitle={laneTitleById}
                        onSelect={() => onSelectNode(nodeId)}
                        onLinkClick={onLinkClick}
                      />
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}
