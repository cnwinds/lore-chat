import type { ApiPersona } from "../../api/openApi";
import type { ChannelInstance, ChannelType } from "../../api/channelPlugins";
import { formatOpenApiWhen } from "../settings/openApiSettingsModel";
import { ChannelDetails } from "./ChannelDetails";
import {
  NEW_EXCLUSIVE_VALUE,
  credentialChip,
  isExclusiveTo,
  isScriptRevoked,
  personaOptionLabel,
  personasSelectableFor,
  statusLabel,
  typeBadgeLabel,
  type DetailTab,
} from "./channelUiModel";

type Props = {
  inst: ChannelInstance;
  types: ChannelType[];
  personas: ApiPersona[];
  usage: Map<string, string[]>;
  busy: boolean;
  activeTab: DetailTab | null;
  editingPrompt: boolean;
  editName: string;
  editPrompt: string;
  onToggle: (inst: ChannelInstance) => void;
  onToggleOutput: (
    inst: ChannelInstance,
    field: "show_thinking" | "show_tool_output",
  ) => void;
  onCopy: (inst: ChannelInstance) => void;
  onToggleTab: (id: string, tab: DetailTab) => void;
  onSelectPersona: (inst: ChannelInstance, value: string) => void;
  onStartEditPrompt: (inst: ChannelInstance) => void;
  onEditName: (value: string) => void;
  onEditPrompt: (value: string) => void;
  onSavePrompt: (inst: ChannelInstance) => void;
  onCancelEditPrompt: () => void;
  onRevoke: (id: string) => void;
};

export function ChannelCard({
  inst,
  types,
  personas,
  usage,
  busy,
  activeTab,
  editingPrompt,
  editName,
  editPrompt,
  onToggle,
  onToggleOutput,
  onCopy,
  onToggleTab,
  onSelectPersona,
  onStartEditPrompt,
  onEditName,
  onEditPrompt,
  onSavePrompt,
  onCancelEditPrompt,
  onRevoke,
}: Props) {
  const status = statusLabel(inst);
  const chip = credentialChip(inst);
  const selectable = personasSelectableFor(personas, inst.id, usage);
  const exclusive =
    Boolean(inst.persona_id) &&
    isExclusiveTo(inst.persona_id || "", inst.id, usage);
  const revoked = isScriptRevoked(inst);
  const typeName = typeBadgeLabel(inst.type_id, types);

  return (
    <li
      className={`channel-card channel-card--${inst.type_id}${inst.enabled ? "" : " channel-card--off"}`}
    >
      <div className="channel-card-main">
        <div className="channel-card-top">
          <div className="channel-card-identity">
            <h4 className="channel-card-title">{inst.name}</h4>
            <span className={`channel-type-badge channel-type-badge--${inst.type_id}`}>
              {typeName}
            </span>
            {status.kind === "error" ? (
              <span className="channel-card-alert">{status.text}</span>
            ) : null}
          </div>
          <ChannelSwitch
            on={inst.enabled}
            label={inst.enabled ? "停用通道" : "启用通道"}
            disabled={busy}
            onClick={() => onToggle(inst)}
          />
        </div>

        {revoked ? (
          <div className="channel-vault channel-vault--revoked" role="status">
            <div className="channel-vault-row">
              <span className="channel-vault-kicker">KEY</span>
              <span className="channel-vault-void" aria-hidden>
                ••••••••••••
              </span>
              <span className="channel-vault-seal">已吊销</span>
            </div>
            <p className="channel-vault-hint">
              这把 Key 已失效，外部无法再调用。打开开关可重新启用同一把 Key。
            </p>
          </div>
        ) : (
          <div className="channel-vault">
            <div className="channel-vault-row">
              <span className="channel-vault-kicker">
                {chip.kind === "token" ? "KEY" : "凭证"}
              </span>
              <code className="channel-vault-text">{chip.text}</code>
              <span className="channel-vault-meta">
                {chip.kind === "token"
                  ? formatOpenApiWhen(inst.last_event_at)
                  : inst.enabled
                    ? "已保存"
                    : "停用中"}
              </span>
              {chip.copyable ? (
                <button
                  type="button"
                  className="channel-vault-copy"
                  disabled={busy}
                  onClick={() => onCopy(inst)}
                >
                  复制
                </button>
              ) : null}
            </div>
          </div>
        )}

        <div className="channel-role-row">
          <span className="channel-role-label">角色</span>
          <select
            className="channel-role-select"
            aria-label={`${inst.name} 角色`}
            value={inst.persona_id || ""}
            disabled={busy}
            onChange={(e) => onSelectPersona(inst, e.target.value)}
          >
            {!inst.persona_id ? <option value="">未绑定</option> : null}
            {selectable.map((persona) => (
              <option key={persona.id} value={persona.id}>
                {personaOptionLabel(persona, inst.id, usage)}
              </option>
            ))}
            <option value={NEW_EXCLUSIVE_VALUE}>新建本通道专属…</option>
          </select>
          <button
            type="button"
            className="channel-role-edit"
            disabled={busy || !inst.persona_id}
            onClick={() => onStartEditPrompt(inst)}
          >
            编辑
          </button>
        </div>

        <div className="channel-output-row">
          <span className="channel-role-label">输出</span>
          <div className="channel-output-toggles">
            <div className="channel-output-toggle">
              <span className="channel-output-toggle-name">思考</span>
              <ChannelSwitch
                on={Boolean(inst.show_thinking)}
                label="输出思考"
                disabled={busy}
                compact
                onClick={() => onToggleOutput(inst, "show_thinking")}
              />
            </div>
            <div className="channel-output-toggle">
              <span className="channel-output-toggle-name">工具</span>
              <ChannelSwitch
                on={Boolean(inst.show_tool_output)}
                label="输出工具"
                disabled={busy}
                compact
                onClick={() => onToggleOutput(inst, "show_tool_output")}
              />
            </div>
          </div>
        </div>

        {editingPrompt ? (
          <div className="channel-prompt-edit">
            {exclusive ? null : (
              <p className="channel-panel-muted">
                此角色可能被多个通道共用，改完下一轮都生效。
              </p>
            )}
            <label className="settings-field">
              <span>名称</span>
              <input
                type="text"
                value={editName}
                onChange={(e) => onEditName(e.target.value)}
                disabled={busy}
              />
            </label>
            <label className="settings-field">
              <span>提示词</span>
              <textarea
                rows={3}
                value={editPrompt}
                onChange={(e) => onEditPrompt(e.target.value)}
                disabled={busy}
              />
            </label>
            <div className="openapi-card-actions">
              <button
                type="button"
                className="settings-btn settings-btn--compact settings-btn--primary"
                disabled={busy || !editName.trim()}
                onClick={() => onSavePrompt(inst)}
              >
                保存
              </button>
              <button
                type="button"
                className="openapi-btn"
                disabled={busy}
                onClick={onCancelEditPrompt}
              >
                取消
              </button>
            </div>
          </div>
        ) : null}

        <ChannelDetails
          inst={inst}
          busy={busy}
          activeTab={activeTab}
          onToggleTab={(tab) => onToggleTab(inst.id, tab)}
          onRevoke={onRevoke}
        />
      </div>
    </li>
  );
}

function ChannelSwitch({
  on,
  label,
  disabled,
  onClick,
  compact = false,
}: {
  on: boolean;
  label: string;
  disabled: boolean;
  onClick: () => void;
  compact?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      className={`channel-switch${compact ? " channel-switch--sm" : ""}${on ? " is-on" : ""}`}
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
    >
      <span className="channel-switch-track" aria-hidden>
        <span className="channel-switch-knob" />
      </span>
    </button>
  );
}
