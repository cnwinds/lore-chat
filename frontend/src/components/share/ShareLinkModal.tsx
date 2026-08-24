import { useCallback, useEffect, useState } from "react";
import {
  createShare,
  ttlSecFromPreset,
  type CreateShareRequest,
  type ShareExpiryPreset,
} from "../../api/share";
import { useCopyShareUrl } from "../../hooks/useShareLink";
import { getConversation, getSettings } from "../../api";

export type ShareLinkModalTarget =
  | { type: "conversation"; conversationId: string; defaultTitle: string }
  | { type: "doc"; path: string; defaultTitle: string };

type Props = {
  open: boolean;
  target: ShareLinkModalTarget | null;
  onClose: () => void;
  onOpenSettings?: () => void;
};

const EXPIRY_OPTIONS: { id: ShareExpiryPreset; label: string }[] = [
  { id: "permanent", label: "永久" },
  { id: "1d", label: "24 小时" },
  { id: "7d", label: "7 天" },
  { id: "30d", label: "30 天" },
  { id: "custom", label: "自定义" },
];

function minDatetimeLocal(): string {
  const d = new Date(Date.now() + 60_000);
  d.setSeconds(0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function defaultCustomExpLocal(): string {
  const d = new Date(Date.now() + 7 * 86400 * 1000);
  d.setSeconds(0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const CONVERSATION_CONFIRM =
  "将公开当前全部消息（含引用与附件预览）。分享后原对话可继续，但分享内容为快照。\n\n确定创建分享链接？";

export function ShareLinkModal({ open, target, onClose, onOpenSettings }: Props) {
  const copyUrl = useCopyShareUrl();
  const [title, setTitle] = useState("");
  const [expiry, setExpiry] = useState<ShareExpiryPreset>("7d");
  const [customExp, setCustomExp] = useState(defaultCustomExpLocal);
  const [pinVersion, setPinVersion] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdUrl, setCreatedUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [publicBaseMissing, setPublicBaseMissing] = useState(false);

  useEffect(() => {
    if (!open || !target) return;
    setTitle(target.defaultTitle);
    setExpiry("7d");
    setCustomExp(defaultCustomExpLocal());
    setPinVersion(true);
    setError(null);
    setCreatedUrl(null);
    setCopied(false);
    getSettings()
      .then((s) => {
        const base = typeof s.public_base_url === "string" ? s.public_base_url : "";
        setPublicBaseMissing(!base.trim());
      })
      .catch(() => setPublicBaseMissing(true));
    if (target.type === "conversation") {
      getConversation(target.conversationId)
        .then((c) => {
          const t = (c.title || "").trim();
          if (t) setTitle(t);
        })
        .catch(() => {
          /* keep defaultTitle */
        });
    }
  }, [open, target]);

  const buildRequest = useCallback((): CreateShareRequest | null => {
    if (!target) return null;
    const ttl_sec = ttlSecFromPreset(expiry, expiry === "custom" ? customExp : undefined);
    if (target.type === "conversation") {
      return {
        type: "conversation",
        conversation_id: target.conversationId,
        title: title.trim() || target.defaultTitle,
        ttl_sec,
      };
    }
    return {
      type: "doc",
      path: target.path,
      title: title.trim() || target.defaultTitle,
      ttl_sec,
      options: { pin_version: pinVersion },
    };
  }, [target, title, expiry, customExp, pinVersion]);

  const handleCreate = useCallback(
    async (mode: "create" | "copy" | "preview") => {
      const body = buildRequest();
      if (!body) return;
      if (target?.type === "conversation" && !createdUrl) {
        if (!window.confirm(CONVERSATION_CONFIRM)) return;
      }
      setSubmitting(true);
      setError(null);
      try {
        const res = await createShare(body);
        setCreatedUrl(res.url);
        if (mode === "copy") {
          const ok = await copyUrl(res.url);
          setCopied(ok);
        }
        if (mode === "preview") {
          window.open(res.url, "_blank", "noopener,noreferrer");
        }
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "创建失败";
        if (msg.includes("PUBLIC_BASE_URL") || msg.includes("Public Base URL")) {
          setPublicBaseMissing(true);
          setError("请先在设置 → 模型中配置 Public Base URL");
        } else {
          setError(msg);
        }
      } finally {
        setSubmitting(false);
      }
    },
    [buildRequest, copyUrl, target, createdUrl],
  );

  if (!open || !target) return null;

  const isConversation = target.type === "conversation";
  const customInvalid =
    expiry === "custom" && ttlSecFromPreset("custom", customExp) === null;

  return (
    <div className="modal-overlay" role="presentation" onClick={onClose}>
      <div
        className="modal-card share-link-modal"
        role="dialog"
        aria-labelledby="share-link-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="share-link-title" className="modal-title">
          分享{isConversation ? "对话" : "文档"}
        </h2>

        {publicBaseMissing && (
          <div className="share-link-warning" role="alert">
            创建外链需配置 Public Base URL。
            {onOpenSettings ? (
              <button type="button" className="link-btn" onClick={onOpenSettings}>
                前往设置
              </button>
            ) : null}
          </div>
        )}

        <label className="share-link-field">
          <span>分享标题</span>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={200}
          />
        </label>

        <fieldset className="share-link-field">
          <legend>有效期</legend>
          <div className="share-link-expiry-row">
            {EXPIRY_OPTIONS.map((opt) => (
              <label key={opt.id} className="share-link-expiry-opt">
                <input
                  type="radio"
                  name="share-expiry"
                  checked={expiry === opt.id}
                  onChange={() => setExpiry(opt.id)}
                />
                {opt.label}
              </label>
            ))}
          </div>
          {expiry === "custom" && (
            <label className="share-link-custom-exp">
              <span>到期时间</span>
              <input
                type="datetime-local"
                value={customExp}
                min={minDatetimeLocal()}
                onChange={(e) => setCustomExp(e.target.value)}
              />
            </label>
          )}
        </fieldset>

        {!isConversation && (
          <label className="share-link-checkbox">
            <input
              type="checkbox"
              checked={pinVersion}
              onChange={(e) => setPinVersion(e.target.checked)}
            />
            内容固定为当前版本（不随文档更新）
          </label>
        )}

        {isConversation && (
          <p className="share-link-hint">
            将公开当前全部消息（含引用与附件预览）。分享后原对话可继续，但分享内容为快照。
          </p>
        )}

        {customInvalid && (
          <p className="share-link-error">请选择未来的到期时间</p>
        )}

        {error && <p className="share-link-error">{error}</p>}

        {createdUrl && (
          <div className="share-link-result">
            <input type="text" readOnly value={createdUrl} className="share-link-url" />
            {copied && <span className="share-link-copied">已复制</span>}
          </div>
        )}

        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onClose} disabled={submitting}>
            关闭
          </button>
          {createdUrl ? (
            <>
              <button
                type="button"
                className="btn-secondary"
                onClick={() =>
                  window.open(createdUrl, "_blank", "noopener,noreferrer")
                }
              >
                查看分享页
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={() => void copyUrl(createdUrl).then(setCopied)}
              >
                复制链接
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className="btn-secondary"
                disabled={submitting || publicBaseMissing || customInvalid}
                onClick={() => void handleCreate("create")}
              >
                创建链接
              </button>
              <button
                type="button"
                className="btn-secondary"
                disabled={submitting || publicBaseMissing || customInvalid}
                onClick={() => void handleCreate("preview")}
              >
                创建并查看
              </button>
              <button
                type="button"
                className="btn-primary"
                disabled={submitting || publicBaseMissing || customInvalid}
                onClick={() => void handleCreate("copy")}
              >
                复制链接
              </button>
            </>
          )}
        </div>
        {onOpenSettings ? (
          <p className="share-link-manage">
            <button type="button" className="link-btn" onClick={onOpenSettings}>
              管理全部分享
            </button>
          </p>
        ) : null}
      </div>
    </div>
  );
}
