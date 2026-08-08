type Props = {
  agentMaxToolCalls: number;
  onAgentMaxToolCallsChange: (v: number) => void;
  agentParallelTools: boolean;
  onAgentParallelToolsChange: (v: boolean) => void;
  agentMaxParallel: number;
  onAgentMaxParallelChange: (v: number) => void;
  sandboxEnabled: boolean;
  sandboxTrustMode: boolean;
  onSandboxTrustModeChange: (v: boolean) => void;
  sandboxMirrorRegion: "cn" | "global";
  onSandboxMirrorRegionChange: (v: "cn" | "global") => void;
  saving: boolean;
};

export function AgentSettingsTab({
  agentMaxToolCalls,
  onAgentMaxToolCallsChange,
  agentParallelTools,
  onAgentParallelToolsChange,
  agentMaxParallel,
  onAgentMaxParallelChange,
  sandboxEnabled,
  sandboxTrustMode,
  onSandboxTrustModeChange,
  sandboxMirrorRegion,
  onSandboxMirrorRegionChange,
  saving,
}: Props) {
  return (
    <>
      <div className="settings-group">
        <h3 className="settings-group-title">工具调用</h3>
        <p className="settings-group-hint">控制 Agent 执行工具时的并发与次数限制。</p>
        <label className="settings-field">
          <span>最大工具调用次数</span>
          <input
            type="number"
            min="1"
            value={agentMaxToolCalls}
            onChange={(e) => onAgentMaxToolCallsChange(Number(e.target.value))}
            disabled={saving}
          />
        </label>
        <label className="settings-field settings-field--checkbox">
          <input
            type="checkbox"
            checked={agentParallelTools}
            onChange={(e) => onAgentParallelToolsChange(e.target.checked)}
            disabled={saving}
          />
          <span>允许并行工具调用</span>
        </label>
        <label className="settings-field">
          <span>最大并行数</span>
          <input
            type="number"
            min="1"
            value={agentMaxParallel}
            onChange={(e) => onAgentMaxParallelChange(Number(e.target.value))}
            disabled={!agentParallelTools || saving}
          />
        </label>
      </div>
      <div className="settings-group">
        <h3 className="settings-group-title">沙箱执行</h3>
        <p className="settings-group-hint">
          执行能力由部署决定（是否叠加 docker-compose.sandbox.yml）。默认信任模式：沙箱命令直接执行；关闭后高风险命令会先征询。软件源影响 apt / pip / npm 安装速度与可达性。
        </p>
        <label className="settings-field">
          <span>执行能力（只读）</span>
          <input
            value={sandboxEnabled ? "已启用" : "未启用"}
            readOnly
            className="settings-readonly"
          />
        </label>
        <label className="settings-field settings-field--checkbox">
          <input
            type="checkbox"
            checked={sandboxTrustMode}
            onChange={(e) => onSandboxTrustModeChange(e.target.checked)}
            disabled={saving || !sandboxEnabled}
          />
          <span>信任模式（跳过 sandbox_run 确认，默认开启）</span>
        </label>
        <div className="settings-field">
          <span>软件源</span>
          <div
            className="settings-option-list"
            role="radiogroup"
            aria-label="沙箱软件源"
          >
            <label
              className={`settings-option-card${
                sandboxMirrorRegion === "cn"
                  ? " settings-option-card--active"
                  : ""
              }${
                saving || !sandboxEnabled
                  ? " settings-option-card--disabled"
                  : ""
              }`}
            >
              <input
                type="radio"
                name="sandbox-mirror-region"
                value="cn"
                className="settings-option-card-input"
                checked={sandboxMirrorRegion === "cn"}
                onChange={() => onSandboxMirrorRegionChange("cn")}
                disabled={saving || !sandboxEnabled}
              />
              <span className="settings-option-card-title">国内</span>
              <span className="settings-option-card-desc">
                阿里云 / npmmirror，安装更快
              </span>
            </label>
            <label
              className={`settings-option-card${
                sandboxMirrorRegion === "global"
                  ? " settings-option-card--active"
                  : ""
              }${
                saving || !sandboxEnabled
                  ? " settings-option-card--disabled"
                  : ""
              }`}
            >
              <input
                type="radio"
                name="sandbox-mirror-region"
                value="global"
                className="settings-option-card-input"
                checked={sandboxMirrorRegion === "global"}
                onChange={() => onSandboxMirrorRegionChange("global")}
                disabled={saving || !sandboxEnabled}
              />
              <span className="settings-option-card-title">国外</span>
              <span className="settings-option-card-desc">
                官方源，适合海外网络
              </span>
            </label>
          </div>
        </div>
      </div>
    </>
  );
}
