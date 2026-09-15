import type { RoleSummary } from "../../types/chat";
import type { ApiPersona } from "../../api/openApi";
import type { ChannelType } from "../../api/channelPlugins";
import {
  canSubmitCreateKey,
  type CreateKeyDraft,
  type VoiceMode,
} from "../settings/openApiSettingsModel";
import { TYPE_MARK } from "./channelUiModel";

export function PickTypeScreen({
  types,
  busy,
  onBack,
  onPick,
}: {
  types: ChannelType[];
  busy: boolean;
  onBack: () => void;
  onPick: (typeId: string) => void;
}) {
  const cards =
    types.length > 0
      ? types
      : [
          {
            type_id: "script_api",
            display_name: "脚本 / HTTP",
            available: true,
            ingress: "http_bearer",
            needs_public_url: false,
          },
        ];
  return (
    <div className="channel-panel-page">
      <button type="button" className="openapi-back" onClick={onBack}>
        ← 返回
      </button>
      <ul className="openapi-type-grid">
        {cards.map((item) => (
          <li key={item.type_id}>
            <button
              type="button"
              className={`openapi-type-card${item.available ? "" : " openapi-type-card--soon"}`}
              disabled={busy || !item.available}
              onClick={() => onPick(item.type_id)}
            >
              <span
                className={`openapi-type-icon openapi-type-icon--${item.type_id}`}
                aria-hidden
              >
                {TYPE_MARK[item.type_id] || "·"}
              </span>
              <strong>{item.display_name}</strong>
              {item.available ? null : <span className="openapi-type-soon">即将支持</span>}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function field(
  label: string,
  value: string,
  onChange: (value: string) => void,
  busy: boolean,
  extra?: { password?: boolean; placeholder?: string },
) {
  return (
    <label className="settings-field">
      <span>{label}</span>
      <input
        type={extra?.password ? "password" : "text"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={busy}
        placeholder={extra?.placeholder}
        autoComplete={extra?.password ? "new-password" : "off"}
      />
    </label>
  );
}

function TypeFields({
  typeId,
  draft,
  busy,
  onChange,
}: {
  typeId: string;
  draft: CreateKeyDraft;
  busy: boolean;
  onChange: (next: CreateKeyDraft) => void;
}) {
  if (typeId === "feishu") {
    return (
      <>
        {field("App ID", draft.appId, (v) => onChange({ ...draft, appId: v }), busy, {
          placeholder: "cli_…",
        })}
        {field(
          "App Secret",
          draft.appSecret,
          (v) => onChange({ ...draft, appSecret: v }),
          busy,
          { password: true },
        )}
        {field(
          "Verification Token（可选）",
          draft.verificationToken,
          (v) => onChange({ ...draft, verificationToken: v }),
          busy,
          { password: true },
        )}
        {field(
          "Encrypt Key（可选）",
          draft.encryptKey,
          (v) => onChange({ ...draft, encryptKey: v }),
          busy,
          { password: true },
        )}
        <label className="settings-field">
          <span>接入方式</span>
          <select
            value={draft.ingress}
            onChange={(e) =>
              onChange({
                ...draft,
                ingress: e.target.value as CreateKeyDraft["ingress"],
              })
            }
            disabled={busy}
          >
            <option value="websocket">长连接（推荐）</option>
            <option value="http_webhook">HTTP 回调（当前版本未接入）</option>
          </select>
        </label>
      </>
    );
  }
  if (typeId === "slack") {
    return (
      <>
        {field(
          "Bot Token",
          draft.botToken,
          (v) => onChange({ ...draft, botToken: v }),
          busy,
          { password: true, placeholder: "xoxb-…" },
        )}
        {field(
          "App Token（Socket Mode）",
          draft.appToken,
          (v) => onChange({ ...draft, appToken: v }),
          busy,
          { password: true, placeholder: "xapp-…" },
        )}
        {field(
          "Signing Secret（webhook 时必填）",
          draft.signingSecret,
          (v) => onChange({ ...draft, signingSecret: v }),
          busy,
          { password: true },
        )}
        <label className="settings-field">
          <span>接入方式</span>
          <select
            value={draft.ingress}
            onChange={(e) =>
              onChange({
                ...draft,
                ingress: e.target.value as CreateKeyDraft["ingress"],
              })
            }
            disabled={busy}
          >
            <option value="websocket">Socket Mode（推荐）</option>
            <option value="http_webhook">Events API webhook</option>
          </select>
        </label>
      </>
    );
  }
  if (typeId === "wecom") {
    return (
      <>
        {field("企业 ID", draft.corpId, (v) => onChange({ ...draft, corpId: v }), busy)}
        {field(
          "Agent ID",
          draft.agentId,
          (v) => onChange({ ...draft, agentId: v }),
          busy,
        )}
        {field(
          "Secret",
          draft.corpSecret,
          (v) => onChange({ ...draft, corpSecret: v }),
          busy,
          { password: true },
        )}
        {field(
          "Token",
          draft.wecomToken,
          (v) => onChange({ ...draft, wecomToken: v }),
          busy,
          { password: true },
        )}
        {field(
          "EncodingAESKey",
          draft.encodingAesKey,
          (v) => onChange({ ...draft, encodingAesKey: v }),
          busy,
          { password: true },
        )}
      </>
    );
  }
  if (typeId === "dingtalk") {
    return (
      <>
        {field(
          "AppKey",
          draft.appKey,
          (v) => onChange({ ...draft, appKey: v }),
          busy,
        )}
        {field(
          "AppSecret",
          draft.dingAppSecret,
          (v) => onChange({ ...draft, dingAppSecret: v }),
          busy,
          { password: true },
        )}
        {field(
          "RobotCode（可选）",
          draft.robotCode,
          (v) => onChange({ ...draft, robotCode: v }),
          busy,
        )}
      </>
    );
  }
  return null;
}

export function CreateKeyScreen({
  draft,
  personas,
  roles,
  busy,
  typeId,
  typeLabel: selectedType,
  onChange,
  onBack,
  onSubmit,
}: {
  draft: CreateKeyDraft;
  personas: ApiPersona[];
  roles: RoleSummary[];
  busy: boolean;
  typeId: string;
  typeLabel: string;
  onChange: (next: CreateKeyDraft) => void;
  onBack: () => void;
  onSubmit: () => void;
}) {
  const voiceValue =
    draft.voice === "existing" && draft.personaId
      ? `persona:${draft.personaId}`
      : draft.voice;
  const isIm = ["feishu", "slack", "wecom", "dingtalk"].includes(typeId);

  const setVoice = (value: string) => {
    if (value.startsWith("persona:")) {
      onChange({
        ...draft,
        voice: "existing",
        personaId: value.slice("persona:".length),
      });
      return;
    }
    onChange({ ...draft, voice: value as VoiceMode });
  };

  return (
    <div className="channel-panel-page">
      <button type="button" className="openapi-back" onClick={onBack}>
        ← 返回
      </button>
      <form
        className="openapi-form"
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
      >
        <label className="settings-field">
          <span>名称</span>
          <input
            type="text"
            value={draft.name}
            onChange={(e) => onChange({ ...draft, name: e.target.value })}
            disabled={busy}
            placeholder={
              typeId === "script_api" ? "例如：周报脚本" : `例如：${selectedType}助手`
            }
            autoFocus
          />
        </label>
        <label className="settings-field">
          <span>说话方式</span>
          <select
            value={voiceValue}
            onChange={(e) => setVoice(e.target.value)}
            disabled={busy}
          >
            <option value="default">默认（和通道同名）</option>
            {personas.map((p) => (
              <option key={p.id} value={`persona:${p.id}`}>
                {p.name}
              </option>
            ))}
            <option value="new">新建一套…</option>
            {roles.length > 0 ? (
              <option value="copy">从左栏角色复制…</option>
            ) : null}
          </select>
        </label>
        {draft.voice === "new" ? (
          <>
            <label className="settings-field">
              <span>人设名称</span>
              <input
                type="text"
                value={draft.personaName}
                onChange={(e) =>
                  onChange({ ...draft, personaName: e.target.value })
                }
                disabled={busy}
                placeholder="例如：周报助手"
              />
            </label>
            <label className="settings-field">
              <span>提示词</span>
              <textarea
                rows={3}
                value={draft.personaPrompt}
                onChange={(e) =>
                  onChange({ ...draft, personaPrompt: e.target.value })
                }
                disabled={busy}
                placeholder="怎么说话、做什么（可选）"
              />
            </label>
          </>
        ) : null}
        {draft.voice === "copy" ? (
          <label className="settings-field">
            <span>从哪个角色复制</span>
            <select
              value={draft.copyRoleId}
              onChange={(e) =>
                onChange({ ...draft, copyRoleId: e.target.value })
              }
              disabled={busy}
            >
              <option value="">选择角色…</option>
              {roles.map((role) => (
                <option key={role.id} value={role.id}>
                  {role.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <TypeFields
          typeId={typeId}
          draft={draft}
          busy={busy}
          onChange={onChange}
        />
        {isIm ? (
          <label className="settings-field">
            <span>群聊沙箱白名单（可选）</span>
            <input
              type="text"
              value={draft.sandboxAllowSenders}
              onChange={(e) =>
                onChange({ ...draft, sandboxAllowSenders: e.target.value })
              }
              disabled={busy}
              placeholder="外部用户 id，逗号分隔。空则群聊关闭沙箱"
            />
          </label>
        ) : null}
        <footer className="openapi-form-footer">
          <button
            type="button"
            className="openapi-btn"
            disabled={busy}
            onClick={onBack}
          >
            取消
          </button>
          <button
            type="submit"
            className="settings-btn settings-btn--compact settings-btn--primary"
            disabled={busy || !canSubmitCreateKey(draft, typeId)}
          >
            {busy ? "创建中…" : "创建并启用"}
          </button>
        </footer>
      </form>
    </div>
  );
}

