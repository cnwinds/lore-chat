import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  createShare,
  ttlSecFromPreset,
  type CreateShareRequest,
  type ShareExpiryPreset,
} from "../../api/share";
import { useCopyShareUrl } from "../../hooks/useShareLink";
import { getConversation, getSettings } from "../../api";
import type { ChatMessage } from "../../types/chat";
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

const PASSWORD_MIN = 4;
const PASSWORD_MAX = 128;

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

function messagePreview(msg: ChatMessage): string {
  const text = (msg.text || "").replace(/\s+/g, " ").trim();
  if (text) return text.length > 80 ? `${text.slice(0, 80)}…` : text;
  return msg.role === "user" ? "（用户消息）" : "（助手回复）";
}

function idsInContiguousRange(
  messages: ChatMessage[],
  a: number,
  b: number,
): string[] {
  const lo = Math.min(a, b);
  const hi = Math.max(a, b);
  const ids: string[] = [];
  for (let i = lo; i <= hi; i++) {
    const id = messages[i]?.id;
    if (id) ids.push(id);
  }
  return ids;
}

function buildConfirmCopy(opts: {
  kind: "conversation" | "doc";
  rangeCount: number | null;
  hasPassword: boolean;
  pinVersion?: boolean;
}): string {
  const parts: string[] = [];
  if (opts.kind === "conversation") {
    if (opts.pinVersion === false) {
      parts.push("访客将看到会话的最新消息（随对话继续更新）");
    } else if (opts.rangeCount != null) {
      parts.push(`将公开所选 ${opts.rangeCount} 条消息（含引用与附件预览）`);
    } else {
      parts.push("将公开当前全部消息（含引用与附件预览）");
    }
    if (opts.pinVersion !== false) {
      parts.push("分享后原对话可继续，但分享页内容为创建时的快照");
    }
  } else {
    parts.push(
      opts.pinVersion
        ? "将公开当前文档定版内容"
        : "将公开文档链接（内容随后续编辑变化）",
    );
  }
  if (opts.hasPassword) {
    parts.push("访问需密码");
  }
  return `${parts.join("。")}。\n\n确定创建分享链接？`;
}

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
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [rangeMode, setRangeMode] = useState<"all" | "range">("all");
  const [rangeAnchor, setRangeAnchor] = useState<number | null>(null);
  const [rangeEnd, setRangeEnd] = useState<number | null>(null);
  const [usePassword, setUsePassword] = useState(false);
  const [password, setPassword] = useState("");

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
    setRangeMode("all");
    setRangeAnchor(null);
    setRangeEnd(null);
    setUsePassword(false);
    setPassword("");
    setMessages([]);
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
      setMessagesLoading(true);
      getConversation(target.conversationId)
        .then((c) => {
          if (cancelled) return;
          const t = (c.title || "").trim();
          if (t) setTitle(t);
          setMessages(Array.isArray(c.messages) ? c.messages : []);
        })
        .catch(() => {
          /* keep defaultTitle */
        })
        .finally(() => {
          if (!cancelled) setMessagesLoading(false);
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

  const selectedMessageIds = useMemo(() => {
    if (rangeMode !== "range" || rangeAnchor == null || rangeEnd == null) {
      return null;
    }
    return idsInContiguousRange(messages, rangeAnchor, rangeEnd);
  }, [rangeMode, rangeAnchor, rangeEnd, messages]);

  const rangeLo =
    rangeAnchor != null && rangeEnd != null
      ? Math.min(rangeAnchor, rangeEnd)
      : rangeAnchor;
  const rangeHi =
    rangeAnchor != null && rangeEnd != null
      ? Math.max(rangeAnchor, rangeEnd)
      : rangeAnchor;

  const handlePickMessage = (index: number) => {
    if (rangeMode !== "range") return;
    if (rangeAnchor == null || (rangeAnchor != null && rangeEnd != null)) {
      setRangeAnchor(index);
      setRangeEnd(null);
      return;
    }
    setRangeEnd(index);
  };

  const passwordInvalid =
    usePassword &&
    (password.length < PASSWORD_MIN || password.length > PASSWORD_MAX);
  const rangeIncomplete =
    rangeMode === "range" &&
    (selectedMessageIds == null || selectedMessageIds.length === 0);

  const buildRequest = useCallback((): CreateShareRequest | null => {
    if (!target) return null;
    const ttl_sec = ttlSecFromPreset(expiry, expiry === "custom" ? customExp : undefined);
    const pw = usePassword ? password.trim() : undefined;
    if (target.type === "conversation") {
      return {
        type: "conversation",
        conversation_id: target.conversationId,
        title: title.trim() || target.defaultTitle,
        ttl_sec,
        options: { pin_version: pinVersion },
        ...(pinVersion && selectedMessageIds?.length
          ? { message_ids: selectedMessageIds }
          : {}),
        ...(pw ? { password: pw } : {}),
      };
    }
    return {
      type: "doc",
      path: target.path,
      title: title.trim() || target.defaultTitle,
      ttl_sec,
      options: { pin_version: pinVersion },
      ...(pw ? { password: pw } : {}),
    };
  }, [
    target,
    title,
    expiry,
    customExp,
    pinVersion,
    selectedMessageIds,
    usePassword,
    password,
  ]);

  const handleCreate = useCallback(
    async (mode: "copy" | "preview") => {
      const body = buildRequest();
      if (!body) return;
      if (passwordInvalid || rangeIncomplete) return;
      const hasPw = usePassword && !!password.trim();
      if (target?.type === "conversation") {
        if (
          !window.confirm(
            buildConfirmCopy({
              kind: "conversation",
              rangeCount: pinVersion ? selectedMessageIds?.length ?? null : null,
              hasPassword: hasPw,
              pinVersion,
            }),
          )
        ) {
          return;
        }
      } else if (target?.type === "doc" && hasPw) {
        if (
          !window.confirm(
            buildConfirmCopy({
              kind: "doc",
              rangeCount: null,
              hasPassword: true,
              pinVersion: pinVersion,
            }),
          )
        ) {
          return;
        }
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
    [
      buildRequest,
      copyUrl,
      target,
      passwordInvalid,
      rangeIncomplete,
      selectedMessageIds,
      usePassword,
      password,
      pinVersion,
    ],
  );

  if (!open || !target) return null;

  const isConversation = target.type === "conversation";
  const customInvalid =
    expiry === "custom" && ttlSecFromPreset("custom", customExp) === null;
  const followLive = isConversation && !pinVersion;
  const disabled =
    submitting ||
    publicBaseMissing ||
    customInvalid ||
    passwordInvalid ||
    (rangeIncomplete && pinVersion);

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
                ? followLive
                  ? "生成只读外链，访客可查看该对话的最新内容"
                  : "生成只读外链，内容为当前消息快照"
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
              {usePassword ? " · 需密码访问" : ""}
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
              <>
                <label className="share-modal-option-card">
                  <input
                    type="checkbox"
                    checked={!pinVersion}
                    onChange={(e) => {
                      const live = e.target.checked;
                      setPinVersion(!live);
                      if (live) {
                        setRangeMode("all");
                        setRangeAnchor(null);
                        setRangeEnd(null);
                      }
                    }}
                  />
                  <span className="share-modal-option-copy">
                    <strong>跟随会话更新</strong>
                    <span>访客打开链接时看到该对话的最新消息</span>
                  </span>
                </label>

                <div className="share-modal-field">
                  <span className="share-modal-label" id="share-range-label">
                    消息范围
                  </span>
                  {followLive ? (
                    <div className="share-modal-callout">
                      跟随更新模式下将始终展示全部消息；关闭后可选择快照区间。
                    </div>
                  ) : (
                    <>
                <div
                  className="share-modal-range-toggle"
                  role="radiogroup"
                  aria-labelledby="share-range-label"
                >
                  <button
                    type="button"
                    role="radio"
                    aria-checked={rangeMode === "all"}
                    className={`share-modal-expiry-pill${rangeMode === "all" ? " share-modal-expiry-pill--active" : ""}`}
                    onClick={() => {
                      setRangeMode("all");
                      setRangeAnchor(null);
                      setRangeEnd(null);
                    }}
                  >
                    全部
                  </button>
                  <button
                    type="button"
                    role="radio"
                    aria-checked={rangeMode === "range"}
                    className={`share-modal-expiry-pill${rangeMode === "range" ? " share-modal-expiry-pill--active" : ""}`}
                    onClick={() => setRangeMode("range")}
                  >
                    选择区间
                  </button>
                </div>
                {rangeMode === "range" && (
                  <div className="share-modal-msg-list" role="listbox" aria-label="选择消息区间">
                    {messagesLoading ? (
                      <p className="share-modal-msg-hint">加载消息…</p>
                    ) : !messages.length ? (
                      <p className="share-modal-msg-hint">暂无消息可分享</p>
                    ) : (
                      <>
                        <p className="share-modal-msg-hint">
                          {rangeAnchor == null
                            ? "点击选择起点"
                            : rangeEnd == null
                              ? "再点击选择终点"
                              : `已选 ${selectedMessageIds?.length ?? 0} 条`}
                        </p>
                        <ul className="share-modal-msg-ul">
                          {messages.map((msg, index) => {
                            const inRange =
                              rangeLo != null &&
                              rangeHi != null &&
                              index >= rangeLo &&
                              index <= rangeHi;
                            const isEndpoint =
                              index === rangeAnchor || index === rangeEnd;
                            return (
                              <li key={msg.id || `idx-${index}`}>
                                <button
                                  type="button"
                                  role="option"
                                  aria-selected={inRange}
                                  className={`share-modal-msg-item${inRange ? " share-modal-msg-item--in" : ""}${isEndpoint ? " share-modal-msg-item--end" : ""}`}
                                  onClick={() => handlePickMessage(index)}
                                >
                                  <span className="share-modal-msg-role">
                                    {msg.role === "user" ? "你" : "助手"}
                                  </span>
                                  <span className="share-modal-msg-text">
                                    {messagePreview(msg)}
                                  </span>
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      </>
                    )}
                  </div>
                )}
                {rangeMode === "all" && (
                  <div className="share-modal-callout">
                    将公开当前全部消息（含引用与附件预览）。原对话可继续，但分享页内容为创建时的快照。
                  </div>
                )}
                    </>
                  )}
                </div>
              </>
            )}

            <div className="share-modal-field">
              <label className="share-modal-option-card">
                <input
                  type="checkbox"
                  checked={usePassword}
                  onChange={(e) => {
                    setUsePassword(e.target.checked);
                    if (!e.target.checked) setPassword("");
                  }}
                />
                <span className="share-modal-option-copy">
                  <strong>设置访问密码</strong>
                  <span>访客需输入密码后才能查看内容</span>
                </span>
              </label>
              {usePassword && (
                <input
                  type="password"
                  className="share-modal-input"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  minLength={PASSWORD_MIN}
                  maxLength={PASSWORD_MAX}
                  placeholder={`${PASSWORD_MIN}–${PASSWORD_MAX} 个字符`}
                  autoComplete="new-password"
                  aria-label="访问密码"
                />
              )}
              {passwordInvalid && (
                <p className="share-modal-error">
                  密码长度须为 {PASSWORD_MIN}–{PASSWORD_MAX} 个字符
                </p>
              )}
            </div>

            {customInvalid && (
              <p className="share-modal-error">请选择未来的到期时间</p>
            )}
            {rangeIncomplete && pinVersion && (
              <p className="share-modal-error">请选择完整的消息区间</p>
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
