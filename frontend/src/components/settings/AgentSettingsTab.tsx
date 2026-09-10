type Props = {
  agentMaxToolCalls: number;
  onAgentMaxToolCallsChange: (v: number) => void;
  agentParallelTools: boolean;
  onAgentParallelToolsChange: (v: boolean) => void;
  agentMaxParallel: number;
  onAgentMaxParallelChange: (v: number) => void;
  continuityIdleHours: number;
  onContinuityIdleHoursChange: (v: number) => void;
  sandboxEnabled: boolean;
  sandboxTrustMode: boolean;
  onSandboxTrustModeChange: (v: boolean) => void;
  sandboxMirrorRegion: "cn" | "global";
  onSandboxMirrorRegionChange: (v: "cn" | "global") => void;
  sandboxMaxRoles: number;
  onSandboxMaxRolesChange: (v: number) => void;
  sandboxIdleTtlSec: number;
  onSandboxIdleTtlSecChange: (v: number) => void;
  sandboxDestroyVolumeOnRoleDelete: boolean;
  onSandboxDestroyVolumeOnRoleDeleteChange: (v: boolean) => void;
  saving: boolean;
};

export function AgentSettingsTab({
  agentMaxToolCalls,
  onAgentMaxToolCallsChange,
  agentParallelTools,
  onAgentParallelToolsChange,
  agentMaxParallel,
  onAgentMaxParallelChange,
  continuityIdleHours,
  onContinuityIdleHoursChange,
  sandboxEnabled,
  sandboxTrustMode,
  onSandboxTrustModeChange,
  sandboxMirrorRegion,
  onSandboxMirrorRegionChange,
  sandboxMaxRoles,
  onSandboxMaxRolesChange,
  sandboxIdleTtlSec,
  onSandboxIdleTtlSecChange,
  sandboxDestroyVolumeOnRoleDelete,
  onSandboxDestroyVolumeOnRoleDeleteChange,
  saving,
}: Props) {
  return (
    <>
      <div className="settings-group">
        <h3 className="settings-group-title">连续窗口</h3>
        <p className="settings-group-hint">
          同一角色下，距上次用户消息未超过该时长则续聊活跃线；超时则静默开启新话题。与记忆抽取空闲时间（默认
          24 小时）无关。
        </p>
        <label className="settings-field">
          <span>连续窗口（小时）</span>
          <input
            type="number"
            min="0.5"
            max="168"
            step="0.5"
            value={continuityIdleHours}
            onChange={(e) =>
              onContinuityIdleHoursChange(Number(e.target.value))
            }
            disabled={saving}
          />
        </label>
      </div>
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
          执行能力由部署决定（是否叠加 docker-compose.sandbox.yml）。默认信任模式：沙箱命令直接执行；关闭后高风险命令会先征询。软件源影响 apt / pip / npm 安装速度与可达性。每个角色固定自己的执行沙箱；池满时不会借用其他角色。
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
        <label className="settings-field">
          <span>最大并行角色数</span>
          <input
            type="number"
            min="1"
            max="32"
            step="1"
            value={sandboxMaxRoles}
            onChange={(e) => onSandboxMaxRolesChange(Number(e.target.value))}
            disabled={saving || !sandboxEnabled}
          />
        </label>
        <label className="settings-field">
          <span>空闲回收（秒）</span>
          <input
            type="number"
            min="0"
            step="60"
            value={sandboxIdleTtlSec}
            onChange={(e) => onSandboxIdleTtlSecChange(Number(e.target.value))}
            disabled={saving || !sandboxEnabled}
          />
        </label>
        <p className="settings-group-hint">
          超过该秒数且没有正在执行的命令时，只关掉该角色的容器，工作区卷仍保留。填 0 表示不自动回收。
        </p>
        <label className="settings-field settings-field--checkbox">
          <input
            type="checkbox"
            checked={sandboxDestroyVolumeOnRoleDelete}
            onChange={(e) =>
              onSandboxDestroyVolumeOnRoleDeleteChange(e.target.checked)
            }
            disabled={saving || !sandboxEnabled}
          />
          <span>删除角色时丢弃其工作区卷（默认关闭，只停容器）</span>
        </label>
      </div>
    </>
  );
}
