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
  revokeTabLabel,
  statusLabel,
  typeLabel,
} from "./channelUiModel";

type Props = {
  inst: ChannelInstance;
  types: ChannelType[];
  personas: ApiPersona[];
  usage: Map<string, string[]>;
  busy: boolean;
  detailsOpen: boolean;
  editingPrompt: boolean;
  editName: string;
  editPrompt: string;
  onToggle: (inst: ChannelInstance) => void;
  onCopy: (inst: ChannelInstance) => void;
  onToggleDetails: (id: string) => void;
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
  detailsOpen,
  editingPrompt,
  editName,
  editPrompt,
  onToggle,
  onCopy,
  onToggleDetails,
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
  const ingress = inst.config?.ingress;
  const revokeLabel = revokeTabLabel(inst.type_id);

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
            <span className="channel-switch-label">启用</span>
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
          {ingress === "websocket" ? " · 长连接" : ""}
        </p>

        <div className="channel-cred">
          <div className="channel-cred-chip">
            {chip.kind === "token" ? (
              <span className="channel-cred-kicker">KEY</span>
            ) : null}
            <code className="channel-cred-text">{chip.text}</code>
            <span className="channel-cred-hint">
              {chip.kind === "token"
                ? formatOpenApiWhen(inst.last_event_at)
                : "—"}
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

        <button
          type="button"
          className="channel-details-toggle"
          aria-expanded={detailsOpen}
          onClick={() => onToggleDetails(inst.id)}
        >
          <span>
            详情
            <em>
              接入说明 · 会话 · 日志 · {revokeLabel}
            </em>
          </span>
          <span aria-hidden>{detailsOpen ? "▾" : "›"}</span>
        </button>
      </div>
      {detailsOpen ? (
        <ChannelDetails inst={inst} busy={busy} onRevoke={onRevoke} />
      ) : null}
    </li>
  );
}
