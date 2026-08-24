import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
  createShare,
  ttlSecFromPreset,
  type CreateShareRequest,
  type ShareExpiryPreset,
} from "../../api/share";
import { useCopyShareUrl } from "../../hooks/useShareLink";
import { getConversation, getSettings } from "../../api";
import { showToast } from "../../utils/toast";

export type ShareLinkModalTarget =
  | { type: "conversation"; conversationId: string; defaultTitle: string }
  | { type: "doc"; path: string; defaultTitle: string };

type Props = {
  open: boolean;
  target: ShareLinkModalTarget | null;
  onClose: () => void;
  /** 打开设置 → 分享 Tab */
  onOpenShareSettings?: () => void;
  /** 打开设置 → 模型 Tab（配置 Public Base URL） */
  onOpenModelSettings?: () => void;
};

const EXPIRY_OPTIONS: { id: ShareExpiryPreset; label: string; hint?: string }[] = [
  { id: "1d", label: "24 小时" },
  { id: "7d", label: "7 天", hint: "推荐" },
  { id: "30d", label: "30 天" },
  { id: "permanent", label: "永久" },
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

function ShareTypeIcon({ kind }: { kind: "conversation" | "doc" }) {
  return (
    <span
      className={`share-modal-type-icon share-modal-type-icon--${kind}`}
      aria-hidden
    />
  );
}

export function ShareLinkModal({
  open,
  target,
  onClose,
  onOpenShareSettings,
  onOpenModelSettings,
}: Props) {
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
    let cancelled = false;
    setTitle(target.defaultTitle);
    setExpiry("7d");
    setCustomExp(defaultCustomExpLocal());
    setPinVersion(true);
    setError(null);
    setCreatedUrl(null);
    setCopied(false);
    getSettings()
      .then((s) => {
        if (cancelled) return;
        const base = typeof s.public_base_url === "string" ? s.public_base_url : "";
        setPublicBaseMissing(!base.trim());
      })
      .catch(() => {
        if (!cancelled) setPublicBaseMissing(true);
      });
    if (target.type === "conversation") {
      getConversation(target.conversationId)
        .then((c) => {
          if (cancelled) return;
          const t = (c.title || "").trim();
          if (t) setTitle(t);
        })
        .catch(() => {
          /* keep defaultTitle */
        });
    }
    return () => {
      cancelled = true;
    };
  }, [open, target]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      e.preventDefault();
      e.stopPropagation();
      onClose();
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open, onClose]);

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
    async (mode: "copy" | "preview") => {
      const body = buildRequest();
      if (!body) return;
      if (target?.type === "conversation") {
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
          if (ok) showToast("链接已复制");
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
    [buildRequest, copyUrl, target],
  );

  if (!open || !target) return null;

  const isConversation = target.type === "conversation";
  const customInvalid =
    expiry === "custom" && ttlSecFromPreset("custom", customExp) === null;
  const disabled = submitting || publicBaseMissing || customInvalid;

  return createPortal(
    <div className="modal-backdrop share-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal-panel share-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="share-link-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="share-modal-header">
          <ShareTypeIcon kind={target.type} />
          <div className="share-modal-header-text">
            <h3 id="share-link-title">分享{isConversation ? "对话" : "文档"}</h3>
            <p className="share-modal-subtitle">
              {isConversation
                ? "生成只读外链，内容为当前消息快照"
                : target.path}
            </p>
          </div>
        </header>

        {publicBaseMissing && (
          <div className="share-modal-alert share-modal-alert--warn" role="alert">
            <span>创建外链需先配置 Public Base URL</span>
            {onOpenModelSettings ? (
              <button type="button" className="share-modal-link-btn" onClick={onOpenModelSettings}>
                前往设置
              </button>
            ) : null}
          </div>
        )}

        {createdUrl ? (
          <div className="share-modal-success">
            <div className="share-modal-success-badge" aria-hidden />
            <p className="share-modal-success-title">链接已创建</p>
            <p className="share-modal-success-hint">
              {copied ? "链接已复制到剪贴板" : "可复制下方链接发送给他人"}
            </p>
            <div className="share-modal-url-box">
              <input
                type="text"
                readOnly
                value={createdUrl}
                className="share-modal-url-input"
                aria-label="分享链接"
              />
              <button
                type="button"
                className="share-modal-url-copy"
                onClick={() =>
                  void copyUrl(createdUrl).then((ok) => {
                    setCopied(ok);
                    if (ok) showToast("链接已复制");
                  })
                }
              >
                {copied ? "已复制" : "复制"}
              </button>
            </div>
          </div>
        ) : (
          <div className="share-modal-body">
            <label className="share-modal-field">
              <span className="share-modal-label">分享标题</span>
              <input
                type="text"
                className="share-modal-input"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={200}
                placeholder={target.defaultTitle}
              />
            </label>

            <div className="share-modal-field">
              <span className="share-modal-label" id="share-expiry-label">
                有效期
              </span>
              <div
                className="share-modal-expiry-grid"
                role="radiogroup"
                aria-labelledby="share-expiry-label"
              >
                {EXPIRY_OPTIONS.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    role="radio"
                    aria-checked={expiry === opt.id}
                    className={`share-modal-expiry-pill${expiry === opt.id ? " share-modal-expiry-pill--active" : ""}`}
                    onClick={() => setExpiry(opt.id)}
                  >
                    {opt.label}
                    {opt.hint ? (
                      <span className="share-modal-expiry-hint">{opt.hint}</span>
                    ) : null}
                  </button>
                ))}
              </div>
              {expiry === "custom" && (
                <input
                  type="datetime-local"
                  className="share-modal-input share-modal-datetime"
                  value={customExp}
                  min={minDatetimeLocal()}
                  onChange={(e) => setCustomExp(e.target.value)}
                  aria-label="自定义到期时间"
                />
              )}
            </div>

            {!isConversation && (
              <label className="share-modal-option-card">
                <input
                  type="checkbox"
                  checked={pinVersion}
                  onChange={(e) => setPinVersion(e.target.checked)}
                />
                <span className="share-modal-option-copy">
                  <strong>固定当前版本</strong>
                  <span>分享内容不随文档后续编辑变化</span>
                </span>
              </label>
            )}

            {isConversation && (
              <div className="share-modal-callout">
                将公开当前全部消息（含引用与附件预览）。原对话可继续，但分享页内容为创建时的快照。
              </div>
            )}

            {customInvalid && (
              <p className="share-modal-error">请选择未来的到期时间</p>
            )}
            {error && <p className="share-modal-error">{error}</p>}
          </div>
        )}

        <footer className="share-modal-footer">
          <div className="share-modal-actions">
            <button type="button" className="btn-secondary" onClick={onClose} disabled={submitting}>
              {createdUrl ? "完成" : "取消"}
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
                  onClick={() =>
                    void copyUrl(createdUrl).then((ok) => {
                      setCopied(ok);
                      if (ok) showToast("链接已复制");
                    })
                  }
                >
                  复制链接
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  className="btn-secondary"
                  disabled={disabled}
                  onClick={() => void handleCreate("preview")}
                >
                  创建并查看
                </button>
                <button
                  type="button"
                  className="btn-primary"
                  disabled={disabled}
                  onClick={() => void handleCreate("copy")}
                >
                  创建并复制
                </button>
              </>
            )}
          </div>
          {!createdUrl && onOpenShareSettings ? (
            <button type="button" className="share-modal-manage-link" onClick={onOpenShareSettings}>
              管理全部分享 →
            </button>
          ) : null}
        </footer>
      </div>
    </div>,
    document.body,
  );
}
