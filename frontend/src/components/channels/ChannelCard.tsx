import type { ApiPersona } from "../../api/openApi";
import type { ChannelInstance, ChannelType } from "../../api/channelPlugins";
import { formatOpenApiWhen } from "../settings/openApiSettingsModel";
import { ChannelDetails } from "./ChannelDetails";
import {
  NEW_EXCLUSIVE_VALUE,
  TYPE_MARK,
  credentialChip,
  isExclusiveTo,
  personaOptionLabel,
  personasSelectableFor,
  statusLabel,
  typeLabel,
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
  const typeName = typeLabel(inst.type_id, types);

  return (
    <li className={`channel-card channel-card--${inst.type_id}`}>
      <div className="channel-card-main">
        <div className="channel-card-top">
          <div className="channel-card-identity">
            <h4 className="channel-card-title">{inst.name}</h4>
            <span className={`openapi-status openapi-status--${status.kind}`}>
              {status.text}
            </span>
          </div>
          <label className="channel-switch">
            <input
              type="checkbox"
              checked={inst.enabled}
              disabled={busy}
              aria-label={inst.enabled ? "停用通道" : "启用通道"}
              onChange={() => onToggle(inst)}
            />
          </label>
        </div>

        <p className="channel-card-type">
          <span
            className={`openapi-type-icon openapi-type-icon--${inst.type_id}`}
            aria-hidden
          >
            {TYPE_MARK[inst.type_id] || "·"}
          </span>
          {typeName}
          {inst.config?.ingress === "websocket" ? " · 长连接" : ""}
        </p>

        <div className="channel-cred">
          <div className="channel-cred-chip">
            {chip.kind === "token" ? (
              <span className="channel-cred-kicker">KEY</span>
            ) : (
              <span className="channel-cred-kicker">凭证</span>
            )}
            <code className="channel-cred-text">{chip.text}</code>
            <span className="channel-cred-hint">
              {chip.kind === "token"
                ? formatOpenApiWhen(inst.last_event_at)
                : "已保存"}
            </span>
          </div>
          <button
            type="button"
            className="channel-copy-btn"
            disabled={busy}
            onClick={() => onCopy(inst)}
          >
            复制
          </button>
        </div>

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
            className="channel-edit-link"
            disabled={busy || !inst.persona_id}
            onClick={() => onStartEditPrompt(inst)}
          >
            编辑
          </button>
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
