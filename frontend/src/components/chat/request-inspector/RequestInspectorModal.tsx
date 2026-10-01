import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  getConversationRequest,
  getConversationRequestRaw,
  listConversationRequests,
  type RequestCallSummary,
  type RequestDetail,
} from "../../../api";
import { compactTokenCount } from "../../../utils/chatMessageFormat";
import { categoryColor } from "../requestCategories";
import { RequestInspectorCatalog } from "./RequestInspectorCatalog";
import { RequestInspectorTools } from "./RequestInspectorTools";
import { RequestMessageCard } from "./RequestMessageCard";
import {
  buildCatalogGroups,
  scrollToAndFlash,
  type ScrollTarget,
} from "./requestInspectorGroups";
import { statusLabel } from "./requestInspectorStatus";
import { countInTexts, messageSearchTexts, toolSearchTexts } from "./requestSearchText";
import { countMatches, highlightMatches } from "./searchHighlight";

type Props = {
  open: boolean;
  conversationId: string;
  initialCategory: string | null;
  initialCallId: number | "latest" | null;
  onClose: () => void;
};

export function RequestInspectorModal({
  open,
  conversationId,
  initialCategory,
  initialCallId,
  onClose,
}: Props) {
  const [calls, setCalls] = useState<RequestCallSummary[]>([]);
  const [detail, setDetail] = useState<RequestDetail | null>(null);
  const [rawCache, setRawCache] = useState<Record<number, string>>({});
  const [view, setView] = useState<"blocks" | "raw">("blocks");
  const [callId, setCallId] = useState<number | "latest">("latest");
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null);
  const [scrollTarget, setScrollTarget] = useState<ScrollTarget | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeMatch, setActiveMatch] = useState(0);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const toolsRef = useRef<HTMLElement | null>(null);

  const resolvedId = useMemo(() => {
    if (typeof callId === "number") return callId;
    return detail?.id ?? calls[0]?.id ?? null;
  }, [callId, detail, calls]);

  const rawText = resolvedId ? rawCache[resolvedId] ?? null : null;

  const matchLayout = useMemo(() => {
    if (view === "raw") {
      return {
        messageOffsets: [] as number[],
        toolsOffset: 0,
        total: countMatches(rawText ?? "", searchQuery),
      };
    }
    let off = 0;
    const messageOffsets: number[] = [];
    for (const m of detail?.messages ?? []) {
      messageOffsets.push(off);
      off += countInTexts(messageSearchTexts(m), searchQuery);
    }
    const toolsOffset = off;
    for (const t of detail?.tools ?? []) {
      off += countInTexts(toolSearchTexts(t), searchQuery);
    }
    return { messageOffsets, toolsOffset, total: off };
  }, [detail, rawText, searchQuery, view]);
  const hitCount = matchLayout.total;

  const loadCalls = useCallback(async () => {
    const { calls: list } = await listConversationRequests(conversationId);
    setCalls(list);
  }, [conversationId]);

  const loadDetail = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (calls.length === 0 && callId === "latest") {
        setDetail(null);
        return;
      }
      const d = await getConversationRequest(conversationId, callId);
      setDetail(d);
    } catch {
      setError("加载失败");
    } finally {
      setLoading(false);
    }
  }, [conversationId, callId, calls.length]);

  const loadRaw = useCallback(async (id: number) => {
    if (rawCache[id]) return;
    const raw = await getConversationRequestRaw(conversationId, id);
    setRawCache((c) => ({ ...c, [id]: JSON.stringify(raw, null, 2) }));
  }, [conversationId, rawCache]);

  useEffect(() => {
    if (!open) return;
    setCategoryFilter(initialCategory);
    setCallId(initialCallId ?? "latest");
    setView("blocks");
    void loadCalls();
  }, [open, initialCategory, initialCallId, loadCalls]);

  useEffect(() => {
    if (!open) return;
    void loadDetail();
  }, [open, loadDetail]);

  useEffect(() => {
    if (!open || view !== "raw" || resolvedId == null) return;
    void loadRaw(resolvedId);
  }, [open, view, resolvedId, loadRaw]);

  useEffect(() => {
    setActiveMatch(0);
  }, [searchQuery, view, detail, rawText]);

  useEffect(() => {
    if (!open || hitCount === 0) return;
    const mark = dialogRef.current?.querySelector(".reqinspector-mark--active");
    mark?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [open, activeMatch, hitCount, view, detail]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "/" && dialogRef.current?.contains(document.activeElement)) {
        e.preventDefault();
        dialogRef.current.querySelector<HTMLInputElement>(".reqinspector-find-input")?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const turnOrder = useMemo(() => {
    const seen: string[] = [];
    for (const c of [...calls].reverse()) {
      if (!seen.includes(c.turn_id)) seen.push(c.turn_id);
    }
    return seen;
  }, [calls]);

  const groups = useMemo(
    () => (detail ? buildCatalogGroups(detail) : []),
    [detail],
  );

  const callLabel = (c: RequestCallSummary) => {
    const turnIdx = turnOrder.indexOf(c.turn_id) + 1;
    const tok = c.prompt_tokens != null ? compactTokenCount(c.prompt_tokens) : "—";
    const st = statusLabel(c.status);
    const mark = st ? ` · ${st}` : "";
    return `第 ${turnIdx} 回合 · 第 ${c.round} 次 · ${tok}${mark}`;
  };

  const copyContent = () => {
    if (view === "raw" && resolvedId && rawCache[resolvedId]) {
      void navigator.clipboard.writeText(rawCache[resolvedId]);
      return;
    }
    if (!detail) return;
    const parts: string[] = [];
    for (const m of detail.messages) {
      const label = m.segments[0]?.label ?? m.role;
      parts.push(`--- ${m.role} · ${label} ---\n${m.segments.map((s) => s.text).join("")}`);
    }
    for (const t of detail.tools) {
      parts.push(
        `--- 工具定义 · ${t.name} ---\n${t.description}\n${JSON.stringify(t.parameters, null, 2)}`,
      );
    }
    void navigator.clipboard.writeText(parts.join("\n\n"));
  };

  const used = detail?.usage.prompt_tokens ?? null;
  const limit = detail?.limit_tokens ?? null;
  const barDen = limit ?? used;
  const barSegs = (detail?.categories ?? []).filter((c) => c.tokens > 0 && barDen);

  const onNavigate = (target: ScrollTarget) => {
    setCatalogOpen(false);
    if (target.kind === "tools") {
      const root = toolsRef.current;
      const item =
        target.toolIndex != null
          ? root?.querySelector(`[data-tool-index="${target.toolIndex}"]`)
          : null;
      scrollToAndFlash(item ?? root);
      return;
    }
    setScrollTarget(target);
  };

  const goNextMatch = () => {
    if (!hitCount) return;
    setActiveMatch((i) => (i + 1) % hitCount);
  };
  const goPrevMatch = () => {
    if (!hitCount) return;
    setActiveMatch((i) => (i - 1 + hitCount) % hitCount);
  };

  if (!open) return null;

  const statusText = detail ? statusLabel(detail.status) : null;
  const rawHighlight =
    view === "raw" && rawText
      ? highlightMatches(rawText, searchQuery, activeMatch, 0).nodes
      : null;

  return (
    <div className="reqinspector-overlay" role="presentation" onClick={onClose}>
      <div
        ref={dialogRef}
        className="reqinspector"
        role="dialog"
        aria-label="发送内容"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="reqinspector-head">
          <div className="reqinspector-head-start">
            <h3>发送内容</h3>
            <button
              type="button"
              className="reqinspector-catalog-mobile-btn"
              onClick={() => setCatalogOpen((v) => !v)}
            >
              目录
            </button>
            <div className="reqinspector-call-nav" role="group" aria-label="选择请求快照">
              <button
                type="button"
                className="reqinspector-call-step"
                disabled={calls.length < 2}
                onClick={() => {
                  const idx = calls.findIndex((c) => c.id === resolvedId);
                  if (idx < calls.length - 1) setCallId(calls[idx + 1].id);
                }}
                aria-label="上一条快照"
                title="上一条快照"
              >
                ‹
              </button>
              <div className="reqinspector-call-select-wrap">
                <select
                  className="reqinspector-call-select"
                  value={resolvedId ?? ""}
                  onChange={(e) => setCallId(Number(e.target.value))}
                  aria-label="请求快照"
                >
                  {calls.map((c) => (
                    <option key={c.id} value={c.id}>
                      {callLabel(c)}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                className="reqinspector-call-step"
                disabled={calls.length < 2}
                onClick={() => {
                  const idx = calls.findIndex((c) => c.id === resolvedId);
                  if (idx > 0) setCallId(calls[idx - 1].id);
                }}
                aria-label="下一条快照"
                title="下一条快照"
              >
                ›
              </button>
            </div>
            <div className="reqinspector-view-toggle" role="group" aria-label="视图">
              <button
                type="button"
                className={view === "blocks" ? "is-active" : ""}
                onClick={() => setView("blocks")}
              >
                分块
              </button>
              <button
                type="button"
                className={view === "raw" ? "is-active" : ""}
                onClick={() => setView("raw")}
              >
                原始
              </button>
            </div>
          </div>
          <div className="reqinspector-find" role="search">
            <span className="reqinspector-find-icon" aria-hidden>
              ⌕
            </span>
            <input
              className="reqinspector-find-input"
              type="search"
              placeholder="在正文中搜索…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  goNextMatch();
                }
                if (e.key === "Enter" && e.shiftKey) {
                  e.preventDefault();
                  goPrevMatch();
                }
              }}
            />
            <div className="reqinspector-find-meta">
              <span className="reqinspector-find-count" aria-live="polite">
                {searchQuery.trim()
                  ? hitCount > 0
                    ? `${activeMatch + 1} / ${hitCount}`
                    : "无匹配"
                  : "—"}
              </span>
              <div className="reqinspector-find-steps">
                <button
                  type="button"
                  className="reqinspector-find-step"
                  disabled={!hitCount}
                  onClick={goPrevMatch}
                  aria-label="上一处"
                  title="上一处 (Shift+Enter)"
                >
                  上一处
                </button>
                <button
                  type="button"
                  className="reqinspector-find-step"
                  disabled={!hitCount}
                  onClick={goNextMatch}
                  aria-label="下一处"
                  title="下一处 (Enter)"
                >
                  下一处
                </button>
              </div>
            </div>
          </div>
          <div className="reqinspector-head-actions">
            <button type="button" className="reqinspector-copy" onClick={copyContent}>
              复制
            </button>
            <button
              type="button"
              className="reqinspector-close"
              onClick={onClose}
              aria-label="关闭"
            >
              ×
            </button>
          </div>
        </header>
        {loading && !detail ? (
          <p className="reqinspector-empty">加载中…</p>
        ) : error ? (
          <p className="reqinspector-empty">{error}</p>
        ) : !detail && calls.length === 0 ? (
          <p className="reqinspector-empty">还没有发给模型的请求</p>
        ) : detail ? (
          <>
            <div className="reqinspector-summary">
              <span>{detail.model_label ?? detail.model}</span>
              <span>
                实测 {used != null ? compactTokenCount(used) : "—"}
                {limit ? ` / ${compactTokenCount(limit)}` : ""}
              </span>
              {detail.usage.cache_tokens != null ? (
                <span>缓存 {compactTokenCount(detail.usage.cache_tokens)}</span>
              ) : null}
              {detail.usage.completion_tokens != null ? (
                <span>输出 {compactTokenCount(detail.usage.completion_tokens)}</span>
              ) : null}
              {statusText ? (
                <span className="reqinspector-status" title={detail.error ?? ""}>
                  {statusText}
                  {detail.error ? `：${detail.error.slice(0, 80)}` : ""}
                </span>
              ) : null}
              {detail.attempts > 1 ? <span>重试 {detail.attempts} 次</span> : null}
            </div>
            <div className="reqinspector-bar-track">
              {barSegs.map((seg) => (
                <button
                  key={seg.key}
                  type="button"
                  className={`reqinspector-bar-seg${categoryFilter === seg.key ? " is-active" : ""}`}
                  style={{
                    width: `${barDen ? (seg.tokens / barDen) * 100 : 0}%`,
                    background: categoryColor(seg.key),
                  }}
                  onClick={() =>
                    setCategoryFilter((f) => (f === seg.key ? null : seg.key))
                  }
                  title={seg.label}
                />
              ))}
            </div>
            <div className="reqinspector-main">
              <aside
                className={`reqinspector-catalog${catalogOpen ? " is-mobile-open" : ""}`}
              >
                <RequestInspectorCatalog
                  groups={groups}
                  categoryFilter={categoryFilter}
                  onNavigate={onNavigate}
                />
              </aside>
              <div className="reqinspector-content">
                {view === "raw" ? (
                  <>
                    <p className="reqinspector-raw-note">
                      已省略内嵌图片数据与链接签名
                    </p>
                    <pre className="reqinspector-raw">{rawHighlight ?? rawText ?? "…"}</pre>
                  </>
                ) : (
                  <>
                    {detail.messages.map((m) => {
                      const label =
                        m.segments.find((s) => s.kind === "user_text")?.label ??
                        m.segments[0]?.label ??
                        m.role;
                      return (
                        <RequestMessageCard
                          key={m.index}
                          message={m}
                          label={label}
                          categoryFilter={categoryFilter}
                          scrollTarget={scrollTarget}
                          searchQuery={searchQuery}
                          activeMatch={activeMatch}
                          matchOffset={matchLayout.messageOffsets[m.index] ?? 0}
                          onClearScroll={() => setScrollTarget(null)}
                        />
                      );
                    })}
                    <RequestInspectorTools
                      tools={detail.tools}
                      categoryFilter={categoryFilter}
                      searchQuery={searchQuery}
                      activeMatch={activeMatch}
                      matchOffset={matchLayout.toolsOffset}
                      scrollRef={(el) => {
                        toolsRef.current = el;
                      }}
                    />
                  </>
                )}
              </div>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
