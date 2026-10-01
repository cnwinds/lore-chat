import { useMemo, useState } from "react";
import type { BgLane, BgNode, BgOverview } from "../../types/background";
import { NodeConfigTab } from "./NodeConfigTab";
import { PromptViewer } from "./PromptViewer";
import { RecentCallsTab } from "./RecentCallsTab";

type DrawerTab = "overview" | "prompts" | "calls" | "config";

type Props = {
  node: BgNode;
  lane: BgLane | null;
  overview: BgOverview;
  overlay: boolean;
  pauseBusy: boolean;
  onClose: () => void;
  onOpenModelSettings: () => void;
  onPauseChange: (pauseKey: string, paused: boolean) => void;
  onConfigSaved: () => void;
};

export function NodeDetailDrawer({
  node,
  lane,
  overview,
  overlay,
  pauseBusy,
  onClose,
  onOpenModelSettings,
  onPauseChange,
  onConfigSaved,
}: Props) {
  const tabs = useMemo(() => {
    const list: { id: DrawerTab; label: string }[] = [
      { id: "overview", label: "概览" },
    ];
    if (node.prompts.length > 0 || node.guards.length > 0) {
      list.push({ id: "prompts", label: "提示词" });
    }
    if (node.purpose) {
      list.push({ id: "calls", label: "最近调用" });
    }
    if (
      node.settings.length > 0 ||
      node.constants.length > 0 ||
      node.pause_key ||
      lane?.pause_key
    ) {
      list.push({ id: "config", label: "配置" });
    }
    return list;
  }, [node, lane]);

  const [tab, setTab] = useState<DrawerTab>("overview");
  const activeTab = tabs.some((t) => t.id === tab) ? tab : tabs[0]?.id ?? "overview";
  const [variantId, setVariantId] = useState(node.prompts[0]?.id ?? "default");
  const variant =
    node.prompts.find((p) => p.id === variantId) ?? node.prompts[0] ?? null;

  const chainSummary = node.chain ? overview.chains[node.chain] : null;

  return (
    <aside
      className={`bgflow-drawer${overlay ? " bgflow-drawer--overlay" : ""}`}
      aria-label="节点详情"
    >
      <div className="bgflow-drawer-head">
        <h3>{node.title}</h3>
        <button type="button" className="bgflow-close" onClick={onClose} aria-label="关闭详情">
          ×
        </button>
      </div>
      <div className="bgflow-drawer-tabs" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={activeTab === t.id}
            className={`bgflow-drawer-tab${activeTab === t.id ? " bgflow-drawer-tab--active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="bgflow-drawer-body">
        {activeTab === "overview" ? (
          <>
            <div className="bgflow-detail-section">
              <p>{node.description}</p>
            </div>
            {lane ? (
              <div className="bgflow-detail-section">
                <h4>何时触发</h4>
                <p>{lane.cadence}</p>
              </div>
            ) : null}
            {node.conditions.length > 0 ? (
              <div className="bgflow-detail-section">
                <h4>前置与跳过</h4>
                <ul className="bgflow-detail-list">
                  {node.conditions.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {node.limits.length > 0 ? (
              <div className="bgflow-detail-section">
                <h4>频率与上限</h4>
                <ul className="bgflow-detail-list">
                  {node.limits.map((l) => (
                    <li key={l}>{l}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {chainSummary ? (
              <div className="bgflow-detail-section">
                <h4>模型链</h4>
                <p>{chainSummary.label}</p>
                <ul className="bgflow-detail-list">
                  {chainSummary.models.map((m) => (
                    <li key={m.model}>
                      {m.label} · {m.model}
                    </li>
                  ))}
                </ul>
                <button type="button" className="bgflow-settings-link" onClick={onOpenModelSettings}>
                  去设置 → 模型修改
                </button>
              </div>
            ) : null}
            {node.temperature != null ? (
              <div className="bgflow-detail-section">
                <h4>温度</h4>
                <p>T={node.temperature}</p>
              </div>
            ) : null}
            {node.outputs.length > 0 ? (
              <div className="bgflow-detail-section">
                <h4>写入</h4>
                <ul className="bgflow-detail-list">
                  {node.outputs.map((o) => (
                    <li key={o}>{o}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {node.source_files.length > 0 ? (
              <div className="bgflow-detail-section">
                <h4>源码</h4>
                <ul className="bgflow-detail-list">
                  {node.source_files.map((f) => (
                    <li key={f}>
                      <code>{f}</code>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        ) : null}

        {activeTab === "prompts" && variant ? (
          <>
            {node.prompts.length > 1 ? (
              <div className="bgflow-variant-tabs">
                {node.prompts.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    className={`bgflow-drawer-tab${variantId === p.id ? " bgflow-drawer-tab--active" : ""}`}
                    onClick={() => setVariantId(p.id)}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            ) : null}
            <PromptViewer variant={variant} />
            {node.guards.length > 0 ? (
              <div className="bgflow-detail-section">
                <h4>代码兜底</h4>
                <ul className="bgflow-detail-list">
                  {node.guards.map((g) => (
                    <li key={g}>{g}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        ) : null}

        {activeTab === "calls" && node.purpose ? (
          <RecentCallsTab purpose={node.purpose} />
        ) : null}

        {activeTab === "config" ? (
          <NodeConfigTab
            node={node}
            lane={lane}
            overview={overview}
            pauseBusy={pauseBusy}
            onPauseChange={onPauseChange}
            onSaved={onConfigSaved}
          />
        ) : null}
      </div>
    </aside>
  );
}
