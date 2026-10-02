import { useCallback, useEffect, useRef, useState } from "react";
import {
  getBackgroundOverview,
  getBackgroundStatus,
  putSettings,
} from "../../api";
import type { BgOverview } from "../../types/background";
import { showToast } from "../../utils/toast";
import { compactTokenCount } from "../../utils/chatMessageFormat";
import { fmtCost } from "../../utils/fmtCost";
import { findLaneForNode, normalizeBgOverview } from "./backgroundUtils";
import { FlowCanvas } from "./FlowCanvas";
import { NodeDetailDrawer } from "./NodeDetailDrawer";

const STATUS_POLL_MS = 10_000;
const NARROW_QUERY = "(max-width: 900px)";

type Props = {
  open: boolean;
  onClose: () => void;
  onOpenModelSettings: () => void;
};

export function BackgroundFlowModal({ open, onClose, onOpenModelSettings }: Props) {
  const [overview, setOverview] = useState<BgOverview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [highlightLaneId, setHighlightLaneId] = useState<string | null>(null);
  const [pauseBusy, setPauseBusy] = useState(false);
  const [stacked, setStacked] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = normalizeBgOverview(await getBackgroundOverview());
      setOverview(data);
    } catch {
      setError("加载后台流程失败");
    } finally {
      setLoading(false);
    }
  }, []);

  const mergeStatus = useCallback(async () => {
    if (!open) return;
    try {
      const status = await getBackgroundStatus();
      setOverview((prev) =>
        prev ? normalizeBgOverview({ ...prev, status }) : prev,
      );
    } catch {
      /* ignore poll errors */
    }
  }, [open]);

  useEffect(() => {
    if (!open) {
      setSelectedNodeId(null);
      setHighlightLaneId(null);
      return;
    }
    void loadOverview();
  }, [open, loadOverview]);

  useEffect(() => {
    if (!open) return;
    const id = window.setInterval(() => void mergeStatus(), STATUS_POLL_MS);
    return () => window.clearInterval(id);
  }, [open, mergeStatus]);

  useEffect(() => {
    if (!open || typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia(NARROW_QUERY);
    const apply = () => setStacked(mql.matches);
    apply();
    mql.addEventListener("change", apply);
    return () => mql.removeEventListener("change", apply);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (selectedNodeId) {
        setSelectedNodeId(null);
        e.stopPropagation();
        return;
      }
      onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, selectedNodeId]);

  const handlePauseChange = async (pauseKey: string, shouldPause: boolean) => {
    if (!overview) return;
    const prev = overview.status.paused;
    const next = shouldPause
      ? [...new Set([...prev, pauseKey])]
      : prev.filter((k) => k !== pauseKey);
    setOverview({
      ...overview,
      status: { ...overview.status, paused: next },
    });
    setPauseBusy(true);
    try {
      await putSettings({ background_paused: next });
      void loadOverview();
    } catch {
      setOverview({
        ...overview,
        status: { ...overview.status, paused: prev },
      });
      showToast("暂停状态保存失败");
    } finally {
      setPauseBusy(false);
    }
  };

  const handleLinkClick = (laneId: string) => {
    setHighlightLaneId(laneId);
    window.setTimeout(() => setHighlightLaneId(null), 2400);
  };

  const handleOpenModelSettings = () => {
    onClose();
    onOpenModelSettings();
  };

  const handleBackdropClick = () => {
    if (selectedNodeId) {
      setSelectedNodeId(null);
      return;
    }
    onClose();
  };

  if (!open) return null;

  const totals = overview?.status.totals_24h;
  const backlog = overview?.status.backlog;
  const selectedNode =
    selectedNodeId && overview ? overview.nodes[selectedNodeId] ?? null : null;
  const selectedLane =
    selectedNode && overview
      ? findLaneForNode(overview.lanes, selectedNode.id)
      : null;

  return (
    <div
      className={`bgflow-overlay${stacked ? " bgflow-overlay--mobile" : ""}`}
      onClick={handleBackdropClick}
    >
      <div
        ref={dialogRef}
        className="bgflow"
        role="dialog"
        aria-modal="true"
        aria-labelledby="bgflow-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="bgflow-head">
          <h2 id="bgflow-title">后台流程</h2>
          <div className="bgflow-legend" aria-hidden>
            <span className="bgflow-legend-item">
              <span className="bgflow-legend-swatch bgflow-legend-swatch--utility" />
              辅助链
            </span>
            <span className="bgflow-legend-item">
              <span className="bgflow-legend-swatch bgflow-legend-swatch--chat" />
              对话链
            </span>
            <span className="bgflow-legend-item">
              <span className="bgflow-legend-swatch bgflow-legend-swatch--embed" />
              嵌入链
            </span>
            <span className="bgflow-legend-item">
              <span className="bgflow-legend-swatch bgflow-legend-swatch--code" />
              代码步骤
            </span>
            <span className="bgflow-legend-item">
              <span className="bgflow-legend-swatch bgflow-legend-swatch--trigger" />
              触发
            </span>
            <span className="bgflow-legend-item">
              <span className="bgflow-legend-swatch bgflow-legend-swatch--store" />
              写入
            </span>
          </div>
          {totals ? (
            <div className="bgflow-summary-bar">
              <span>
                24h 调用 <strong>{totals.calls}</strong>
              </span>
              <span>
                tokens{" "}
                <strong>
                  {compactTokenCount(totals.prompt_tokens)}/
                  {compactTokenCount(totals.completion_tokens)}
                </strong>
              </span>
              <span>
                费用 <strong>{fmtCost(totals.cost, totals.cost != null)}</strong>
              </span>
              <span>
                失败 <strong>{totals.errors}</strong>
              </span>
              {backlog ? (
                <span>
                  待抽取 <strong>{backlog.session_observe_pending}</strong>
                </span>
              ) : null}
            </div>
          ) : null}
          <button type="button" className="bgflow-close" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </header>

        <div className="bgflow-body">
          {loading && !overview ? (
            <p className="bgflow-empty">加载中…</p>
          ) : error && !overview ? (
            <div className="bgflow-error">
              {error}
              <div>
                <button type="button" className="bgflow-retry-btn" onClick={() => void loadOverview()}>
                  重试
                </button>
              </div>
            </div>
          ) : overview ? (
            <>
              <FlowCanvas
                overview={overview}
                stacked={stacked}
                highlightLaneId={highlightLaneId}
                selectedNodeId={selectedNodeId}
                pauseBusy={pauseBusy}
                onSelectNode={(id) =>
                  setSelectedNodeId((cur) => (cur === id ? null : id))
                }
                onLinkClick={handleLinkClick}
                onPauseChange={(key, paused) => void handlePauseChange(key, paused)}
              />
              {selectedNode ? (
                <NodeDetailDrawer
                  node={selectedNode}
                  lane={selectedLane}
                  overview={overview}
                  overlay={stacked}
                  pauseBusy={pauseBusy}
                  onClose={() => setSelectedNodeId(null)}
                  onOpenModelSettings={handleOpenModelSettings}
                  onPauseChange={(key, paused) => void handlePauseChange(key, paused)}
                  onConfigSaved={() => void loadOverview()}
                />
              ) : null}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
