import { useEffect, useRef, type Ref } from "react";
import { ProviderApiKeyLabel } from "./ProviderApiKeyLabel";
import {
  STARTER_AGNES_MODEL,
  STARTER_DEEPSEEK_CHAT_MODEL,
  STARTER_EMBED_MODEL,
  readStarterPackKeys,
  starterPackCanSave,
  type StarterPackDrafts,
  type StarterPackKeys,
  type StarterPackPhase,
} from "./starterPack";

type Props = {
  phase: StarterPackPhase;
  drafts: StarterPackDrafts;
  saving: boolean;
  onApply: () => void;
  onDismiss: () => void;
  onKeysChange: (patch: Partial<StarterPackKeys>) => void;
};

export function StarterPackGuide({
  phase,
  drafts,
  saving,
  onApply,
  onDismiss,
  onKeysChange,
}: Props) {
  if (phase === "hidden") return null;
  if (phase === "offer") {
    return (
      <OfferCard saving={saving} onApply={onApply} onDismiss={onDismiss} />
    );
  }
  return (
    <CollectingCard
      drafts={drafts}
      saving={saving}
      onKeysChange={onKeysChange}
    />
  );
}

function OfferCard({
  saving,
  onApply,
  onDismiss,
}: {
  saving: boolean;
  onApply: () => void;
  onDismiss: () => void;
}) {
  return (
    <section className="settings-starter" aria-labelledby="starter-pack-title">
      <h3 id="starter-pack-title">用免费套餐开始？</h3>
      <p className="settings-starter-lead">
        还没配模型。可以用下面这套组合立刻跑起来，也可以自己选厂家。额度以各厂家页面为准，Lore
        不提供 Key。
      </p>
      <ul className="settings-starter-list">
        <li>
          <strong>对话 / 辅助 · Agnes 2.5 Flash</strong>
          <span>
            {STARTER_AGNES_MODEL}：对话、工具调用、识图、思考。免费额度适合起步；复杂长任务可能不够稳。两处共用同一把
            Key。
          </span>
        </li>
        <li>
          <strong>知识检索 · 硅基流动 bge-m3</strong>
          <span>
            {STARTER_EMBED_MODEL}：中英知识库检索够用，有免费额度。不填也能先聊天，知识召回会不完整。
          </span>
        </li>
        <li>
          <strong>联网搜索 · Tavily</strong>
          <span>新用户通常有试用额度。不填不影响对话，只是不能联网搜。</span>
        </li>
      </ul>
      <p className="settings-starter-note">
        <strong>更好效果：</strong>对话模型建议用 DeepSeek V4 Flash 0731（
        {STARTER_DEEPSEEK_CHAT_MODEL}
        ，按量付费）。免费套餐先用 Agnes 2.5 Flash 跑起来；保存后可在下方把对话换成该模型，辅助可继续用免费
        Flash。
      </p>
      <div className="settings-starter-actions">
        <button
          type="button"
          className="settings-btn settings-btn--primary"
          disabled={saving}
          onClick={onApply}
        >
          使用免费套餐
        </button>
        <button
          type="button"
          className="settings-btn settings-btn--secondary"
          disabled={saving}
          onClick={onDismiss}
        >
          我自己选厂家
        </button>
      </div>
    </section>
  );
}

function CollectingCard({
  drafts,
  saving,
  onKeysChange,
}: {
  drafts: StarterPackDrafts;
  saving: boolean;
  onKeysChange: (patch: Partial<StarterPackKeys>) => void;
}) {
  const firstRef = useRef<HTMLInputElement>(null);
  const keys = readStarterPackKeys(drafts);
  const canSave = starterPackCanSave(drafts);

  useEffect(() => {
    firstRef.current?.focus();
  }, []);

  return (
    <section className="settings-starter" aria-labelledby="starter-pack-title">
      <h3 id="starter-pack-title">免费套餐已填入</h3>
      <p className="settings-starter-lead">
        对话和辅助都是 {STARTER_AGNES_MODEL}（识图、思考、工具），检索是{" "}
        {STARTER_EMBED_MODEL}，搜索是 Tavily。先贴 Agnes Key 就能对话；检索和联网搜索可稍后补。
      </p>
      <div className="settings-starter-keys">
        <KeyField
          inputRef={firstRef}
          providerId="agnes"
          label="Agnes API Key"
          hint={`对话 + 辅助共用 · ${STARTER_AGNES_MODEL}`}
          need="必填"
          value={keys.agnes}
          disabled={saving}
          onChange={(agnes) => onKeysChange({ agnes })}
        />
        <KeyField
          providerId="siliconflow"
          label="硅基流动 API Key"
          hint={`知识检索 · ${STARTER_EMBED_MODEL}`}
          need="建议"
          value={keys.siliconflow}
          disabled={saving}
          onChange={(siliconflow) => onKeysChange({ siliconflow })}
        />
        <KeyField
          providerId="tavily"
          label="Tavily API Key"
          hint="联网搜索"
          need="可选"
          value={keys.tavily}
          disabled={saving}
          onChange={(tavily) => onKeysChange({ tavily })}
        />
      </div>
      <p className="settings-starter-note">
        更好效果：保存后可在下方把<strong>对话模型</strong>换成 DeepSeek V4 Flash 0731（
        {STARTER_DEEPSEEK_CHAT_MODEL}
        ，按量付费）。辅助可继续用免费 Flash。
      </p>
      <div className="settings-starter-actions">
        <button
          type="submit"
          className="settings-btn settings-btn--primary"
          disabled={saving || !canSave}
        >
          {saving ? "保存中…" : "保存并开始对话"}
        </button>
        <p className="settings-starter-foot">下方列表已同步预填，也可直接改。</p>
      </div>
    </section>
  );
}

function KeyField({
  inputRef,
  providerId,
  label,
  hint,
  need,
  value,
  disabled,
  onChange,
}: {
  inputRef?: Ref<HTMLInputElement>;
  providerId: string;
  label: string;
  hint: string;
  need: "必填" | "建议" | "可选";
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="settings-field">
      <ProviderApiKeyLabel
        providerId={providerId}
        label={label}
        trailing={
          <span
            className={`settings-starter-need${need === "必填" ? "" : " settings-starter-need--optional"}`}
          >
            {need}
          </span>
        }
      />
      <span className="settings-starter-key-meta">{hint}</span>
      <input
        ref={inputRef}
        type="password"
        autoComplete="off"
        value={value}
        disabled={disabled}
        placeholder="未设置"
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}
