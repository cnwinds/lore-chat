import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import type { PreceptsUpgradePending } from "../../api";
import {
  assembleMergeDraft,
  assembleMergeSegments,
  buildMergeView,
  defaultHunkPick,
  hunkIndexAtLine,
  hunkTitle,
  pickedHunkText,
  type MergePick,
  type MergeSegment,
  type ViewHunk,
} from "../../utils/preceptsMergeView";

type Props = {
  open: boolean;
  pending: PreceptsUpgradePending;
  proposing: boolean;
  busy: string | null;
  error: string | null;
  onClose: () => void;
  onConfirm: (body: string) => void;
  onDismiss: () => void;
  onUseOfficial: () => void;
};

export function PreceptsUpgradeModal({
  open,
  pending,
  proposing,
  busy,
  error,
  onClose,
  onConfirm,
  onDismiss,
  onUseOfficial,
}: Props) {
  const view = useMemo(
    () => buildMergeView(pending.base, pending.ours, pending.theirs),
    [pending.base, pending.ours, pending.theirs],
  );
  const [selected, setSelected] = useState(0);
  const [picks, setPicks] = useState<MergePick[]>(() =>
    view.hunks.map(defaultHunkPick),
  );
  const [draft, setDraft] = useState(() => assembleMergeDraft(view.regions));
  const draftRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!open) return;
    const nextPicks = view.hunks.map(defaultHunkPick);
    setSelected(0);
    setPicks(nextPicks);
    setDraft(
      pending.proposed_source === "ai" && pending.proposed?.trim()
        ? pending.proposed
        : assembleMergeDraft(view.regions, nextPicks),
    );
    // pending 轮询会换新对象，同一待确认用 created_at
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, pending.created_at, view]);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }
      const typing =
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLInputElement;
      const prev =
        (e.key === "F8" && e.shiftKey) ||
        (e.altKey && e.key === "ArrowUp") ||
        (!typing && e.key === "[");
      const next =
        (e.key === "F8" && !e.shiftKey) ||
        (e.altKey && e.key === "ArrowDown") ||
        (!typing && e.key === "]");
      if (!prev && !next) return;
      e.preventDefault();
      setSelected((i) =>
        prev
          ? Math.max(0, i - 1)
          : Math.min(Math.max(view.hunks.length - 1, 0), i + 1),
      );
    }
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [open, onClose, view.hunks.length]);

  useEffect(() => {
    if (!open) return;
    const el = draftRef.current;
    const hunk = view.hunks[selected];
    const pick = picks[selected] ?? (hunk ? defaultHunkPick(hunk) : "both");
    const needle = hunk ? pickedHunkText(hunk, pick) : "";
    if (!el || !needle) return;
    const at = el.value.indexOf(needle);
    if (at < 0) return;
    const lh = Number.parseFloat(getComputedStyle(el).lineHeight) || 20;
    const line = el.value.slice(0, at).split("\n").length;
    el.scrollTop = Math.max(0, (line - 3) * lh);
  }, [open, selected, picks, view.hunks]);

  const segments = useMemo(
    () => assembleMergeSegments(view.regions, picks),
    [view.regions, picks],
  );

  if (!open) return null;
  const locked = busy !== null;
  const hunkCount = view.hunks.length;
  const hunk = view.hunks[selected];
  const pick = picks[selected] ?? (hunk ? defaultHunkPick(hunk) : "both");

  function pickHunk(nextPick: MergePick) {
    if (!hunk) return;
    const nextPicks = picks.slice();
    nextPicks[selected] = nextPick;
    setPicks(nextPicks);
    setDraft(assembleMergeDraft(view.regions, nextPicks));
  }

  function jump(delta: number) {
    if (!hunkCount) return;
    setSelected((i) => Math.min(hunkCount - 1, Math.max(0, i + delta)));
  }

  return (
    <div className="doc-diff-overlay" role="presentation" onClick={onClose}>
      <div
        className="doc-history-modal doc-history-modal--frame precepts-merge-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="precepts-upgrade-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="doc-diff-header precepts-merge-top">
          <h3 id="precepts-upgrade-title">戒律更新</h3>
          {hunkCount > 0 ? (
            <div className="precepts-merge-nav">
              <button
                type="button"
                className="doc-diff-btn"
                aria-label="上一处改动"
                disabled={selected === 0}
                onClick={() => jump(-1)}
              >
                上一处
              </button>
              <span className="precepts-merge-pos" aria-live="polite">
                {selected + 1}/{hunkCount}
              </span>
              <div className="precepts-merge-jumps" role="tablist" aria-label="改动">
                {view.hunks.map((item, i) => (
                  <button
                    key={`${item.kind}:${item.ours}:${item.theirs}:${i}`}
                    type="button"
                    role="tab"
                    aria-selected={selected === i}
                    title={hunkTitle(item)}
                    className={`precepts-merge-jump${selected === i ? " is-active" : ""}`}
                    onClick={() => setSelected(i)}
                  >
                    {i + 1} {hunkTitle(item)}
                  </button>
                ))}
              </div>
              <button
                type="button"
                className="doc-diff-btn"
                aria-label="下一处改动"
                disabled={selected >= hunkCount - 1}
                onClick={() => jump(1)}
              >
                下一处
              </button>
            </div>
          ) : (
            <p className="precepts-merge-nav-empty">两边已经一样，中间即结果。</p>
          )}
          <button
            type="button"
            className="doc-diff-close"
            onClick={onClose}
            aria-label="关闭"
          >
            ×
          </button>
        </header>
        <div className="precepts-merge-triple">
          <SideDoc
            kind="ours"
            title="现行"
            text={pending.ours}
            hunks={view.hunks}
            selected={selected}
            onSelect={setSelected}
          />
          <section className="precepts-merge-col precepts-merge-col--result">
            <header className="precepts-merge-col-head">
              <label htmlFor="precepts-merge-draft">
                结果
                {proposing ? (
                  <span className="precepts-merge-result-note">正在生成建议稿</span>
                ) : hunk ? (
                  <span className="precepts-merge-result-note">
                    {hunkTitle(hunk)}
                  </span>
                ) : null}
              </label>
              <span className="precepts-merge-legend" aria-hidden>
                <span className="precepts-merge-legend-item is-ours">左</span>
                <span className="precepts-merge-legend-item is-theirs">右</span>
              </span>
              {hunk ? (
                <div className="precepts-merge-picks" role="group" aria-label="这块怎么收">
                  <PickBtn
                    label="用左边"
                    tone="ours"
                    pressed={pick === "ours"}
                    disabled={locked}
                    onClick={() => pickHunk("ours")}
                  />
                  <PickBtn
                    label="两边都留"
                    tone="both"
                    pressed={pick === "both"}
                    disabled={locked}
                    onClick={() => pickHunk("both")}
                  />
                  <PickBtn
                    label="用右边"
                    tone="theirs"
                    pressed={pick === "theirs"}
                    disabled={locked}
                    onClick={() => pickHunk("theirs")}
                  />
                </div>
              ) : null}
            </header>
            {error ? <p className="doc-diff-empty">{error}</p> : null}
            <ResultEditor
              draft={draft}
              segments={segments}
              selected={selected}
              locked={locked}
              textareaRef={draftRef}
              onChange={setDraft}
            />
          </section>
          <SideDoc
            kind="theirs"
            title="官方"
            text={pending.theirs}
            hunks={view.hunks}
            selected={selected}
            onSelect={setSelected}
          />
        </div>
        <footer className="doc-diff-footer precepts-merge-footer">
          <button
            type="button"
            className="doc-diff-btn"
            onClick={onDismiss}
            disabled={locked}
          >
            保持现行
          </button>
          <span className="precepts-merge-footer-spacer" />
          <button
            type="button"
            className="doc-diff-btn"
            onClick={onUseOfficial}
            disabled={locked}
          >
            整篇用官方
          </button>
          <button
            type="button"
            className="doc-diff-btn doc-diff-btn--primary"
            onClick={() => onConfirm(draft)}
            disabled={locked || !draft.trim()}
          >
            写入结果
          </button>
        </footer>
      </div>
    </div>
  );
}

function ResultEditor({
  draft,
  segments,
  selected,
  locked,
  textareaRef,
  onChange,
}: {
  draft: string;
  segments: MergeSegment[];
  selected: number;
  locked: boolean;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  onChange: (next: string) => void;
}) {
  const paintRef = useRef<HTMLPreElement>(null);
  const assembled = useMemo(
    () => segments.map((segment) => segment.text).join(""),
    [segments],
  );
  const paint = draft === assembled
    ? segments
    : [{ origin: "equal" as const, text: draft, hunkIndex: null }];

  useEffect(() => {
    const src = textareaRef.current;
    const dst = paintRef.current;
    if (!src || !dst) return;
    dst.scrollTop = src.scrollTop;
    dst.scrollLeft = src.scrollLeft;
  }, [draft, selected, assembled, textareaRef]);

  return (
    <div className="precepts-merge-result-stack">
      <pre
        ref={paintRef}
        className="precepts-merge-result-paint"
        aria-hidden
      >
        {paint.map((segment, i) => (
          <span
            key={i}
            className={`precepts-merge-origin precepts-merge-origin--${segment.origin}${
              segment.hunkIndex === selected ? " is-active" : ""
            }`}
          >
            {segment.text}
          </span>
        ))}
      </pre>
      <textarea
        id="precepts-merge-draft"
        ref={textareaRef}
        className="doc-precepts-draft precepts-merge-draft"
        value={draft}
        onChange={(e) => onChange(e.target.value)}
        onScroll={() => {
          const src = textareaRef.current;
          const dst = paintRef.current;
          if (!src || !dst) return;
          dst.scrollTop = src.scrollTop;
          dst.scrollLeft = src.scrollLeft;
        }}
        spellCheck={false}
        disabled={locked}
      />
    </div>
  );
}

function SideDoc({
  kind,
  title,
  text,
  hunks,
  selected,
  onSelect,
}: {
  kind: "ours" | "theirs";
  title: string;
  text: string;
  hunks: ViewHunk[];
  selected: number;
  onSelect: (index: number) => void;
}) {
  const scroller = useRef<HTMLPreElement>(null);
  const lines = useMemo(() => (text || "").split("\n"), [text]);
  const ranges = useMemo(
    () => hunks.map((hunk) => (kind === "ours" ? hunk.oursRange : hunk.theirsRange)),
    [hunks, kind],
  );

  useEffect(() => {
    const el = scroller.current?.querySelector("[data-active-conflict]");
    el?.scrollIntoView?.({ block: "center", inline: "nearest" });
  }, [selected, text]);

  return (
    <section
      className={`precepts-merge-col precepts-merge-col--${kind}`}
      aria-label={`${title}，只读`}
    >
      <header className="precepts-merge-col-head">
        <strong>{title}</strong>
      </header>
      <pre ref={scroller} className="precepts-merge-doc">
        {lines.map((line, i) => {
          const hit = hunkIndexAtLine(ranges, i);
          const active = hit === selected;
          return (
            <div
              key={i}
              data-active-conflict={active ? "" : undefined}
              role={hit >= 0 ? "button" : undefined}
              tabIndex={hit >= 0 ? 0 : undefined}
              className={`precepts-merge-doc-line${hit >= 0 ? " is-conflict" : ""}${active ? " is-active" : ""}`}
              onClick={hit >= 0 ? () => onSelect(hit) : undefined}
              onKeyDown={
                hit >= 0
                  ? (e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onSelect(hit);
                      }
                    }
                  : undefined
              }
            >
              <span className="precepts-merge-ln" aria-hidden>
                {i + 1}
              </span>
              <span className="precepts-merge-doc-text">{line || " "}</span>
            </div>
          );
        })}
      </pre>
    </section>
  );
}

function PickBtn({
  label,
  tone,
  pressed,
  disabled,
  onClick,
}: {
  label: string;
  tone: MergePick;
  pressed: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`doc-diff-btn precepts-merge-pick precepts-merge-pick--${tone}${pressed ? " is-pressed" : ""}`}
      aria-pressed={pressed}
      onClick={onClick}
      disabled={disabled}
    >
      {label}
    </button>
  );
}
