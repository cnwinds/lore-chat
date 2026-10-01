import { useCallback, useEffect, useState } from "react";
import { getBackgroundStatus } from "../../api";
import type { BgStatus } from "../../types/background";

const PAUSE_LABELS: Record<string, string> = {
  session_observe: "会话记忆抽取",
  consolidation: "整理",
  persona_evolution: "人设进化",
};

type Props = {
  onOpenBackgroundFlow: () => void;
};

const POLL_MS = 10_000;

export function BackgroundSettingsTab({ onOpenBackgroundFlow }: Props) {
  const [status, setStatus] = useState<BgStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await getBackgroundStatus();
      setStatus(data);
    } catch {
      setError("摘要加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    void load();
    const id = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  const pausedLabels =
    status?.paused.length === 0
      ? "无"
      : status?.paused.map((k) => PAUSE_LABELS[k] ?? k).join("、");

  return (
    <div
      className="settings-tab-panel bgflow-settings-tab"
      role="tabpanel"
      id="settings-panel-background"
      aria-labelledby="settings-tab-background"
    >
      <p className="bgflow-settings-intro">
        除聊天外，系统在后台定时或按需调用模型做记忆抽取、卡片整理等。此处可查看流程、真实调用记录与相关配置；提示词只读，改动须按仓库规范提交。
      </p>

      {loading && !status ? <p className="settings-panel-hint">加载中…</p> : null}
      {error ? (
        <p className="settings-panel-error">
          {error}{" "}
          <button type="button" className="bgflow-settings-link" onClick={() => void load()}>
            重试
          </button>
        </p>
      ) : null}

      {status ? (
        <dl className="bgflow-settings-stats">
          <div className="bgflow-settings-stat">
            <dt>近 24 小时调用</dt>
            <dd>{status.totals_24h.calls}</dd>
          </div>
          <div className="bgflow-settings-stat">
            <dt>近 24 小时失败</dt>
            <dd>{status.totals_24h.errors}</dd>
          </div>
          <div className="bgflow-settings-stat">
            <dt>待抽取会话</dt>
            <dd>{status.backlog.session_observe_pending}</dd>
          </div>
          <div className="bgflow-settings-stat">
            <dt>已暂停</dt>
            <dd>{pausedLabels}</dd>
          </div>
        </dl>
      ) : null}

      <button type="button" className="bgflow-open-flow-btn" onClick={onOpenBackgroundFlow}>
        打开后台流程图
      </button>
    </div>
  );
}
