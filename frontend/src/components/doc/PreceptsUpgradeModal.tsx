import { useEffect, useMemo, useRef, useState } from "react";
import type { PreceptsUpgradePending } from "../../api";
import {
  applyHunkPick,
  firstEdit,
  hunkIndexAtLine,
  hunkTitle,
  initialMergeDraft,
  lineRange,
  locateHunkSpans,
  pickedHunkText,
  replaceSpan,
  shiftSpans,
  type HunkSpan,
  type MergePick,
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
  const [selected, setSelected] = useState(0);
  const [draft, setDraft] = useState(() => initialMergeDraft(pending));
  const [picks, setPicks] = useState<MergePick[]>(() =>
    pending.conflicts.map(() => "both"),
  );
  const [hunkBody, setHunkBody] = useState<string[]>(() =>
    pending.conflicts.map((hunk) => pickedHunkText(hunk, "both")),
  );
  const [spans, setSpans] = useState<Array<HunkSpan | null>>(() =>
    locateHunkSpans(
      initialMergeDraft(pending),
      pending.conflicts.map((hunk) => pickedHunkText(hunk, "both")),
    ),
  );
  const draftRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!open) return;
    const nextDraft = initialMergeDraft(pending);
    const bodies = pending.conflicts.map((hunk) => pickedHunkText(hunk, "both"));
    setSelected(0);
    setDraft(nextDraft);
    setPicks(pending.conflicts.map(() => "both"));
    setHunkBody(bodies);
    setSpans(locateHunkSpans(nextDraft, bodies));
    // pending 轮询会换新对象，同一待确认用 created_at
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, pending.created_at]);

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
          : Math.min(Math.max(pending.conflicts.length - 1, 0), i + 1),
      );
    }
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [open, onClose, pending.conflicts.length]);

  useEffect(() => {
    if (!open) return;
    const el = draftRef.current;
    const span = spans[selected];
    if (!el || !span) return;
    const lh = Number.parseFloat(getComputedStyle(el).lineHeight) || 20;
    const line = el.value.slice(0, span.start).split("\n").length;
    el.scrollTop = Math.max(0, (line - 3) * lh);
  }, [open, selected, spans]);

  const oursRanges = useMemo(
    () => pending.conflicts.map((hunk) => lineRange(pending.ours, hunk.ours)),
    [pending.conflicts, pending.ours],
  );
  const theirsRanges = useMemo(
    () =>
      pending.conflicts.map((hunk) => lineRange(pending.theirs, hunk.theirs)),
    [pending.conflicts, pending.theirs],
  );

  if (!open) return null;
  const locked = busy !== null;
  const conflictCount = pending.conflicts.length;
  const hunk = pending.conflicts[selected];
  const pick = picks[selected] ?? "both";

  function pickHunk(nextPick: MergePick) {
    if (!hunk) return;
    const nextText = pickedHunkText(hunk, nextPick);
    const span = spans[selected];
    let nextDraft: string;
    let nextSpans = spans;
    if (span) {
      nextDraft = replaceSpan(draft, span, nextText);
      const delta = nextText.length - (span.end - span.start);
      nextSpans = spans.map((item, i) => {
        if (!item) return item;
        if (i === selected) {
          return { start: span.start, end: span.start + nextText.length };
        }
        if (item.start >= span.end) {
          return { start: item.start + delta, end: item.end + delta };
        }
        return item;
      });
    } else {
      nextDraft = applyHunkPick(draft, hunk, hunkBody[selected] ?? "", nextPick);
      nextSpans = locateHunkSpans(
        nextDraft,
        hunkBody.map((body, i) => (i === selected ? nextText : body)),
      );
    }
    const nextBodies = nextSpans.map((item, i) =>
      item
        ? nextDraft.slice(item.start, item.end)
        : i === selected
          ? nextText
          : hunkBody[i] ?? "",
    );
    const nextPicks = picks.slice();
    nextPicks[selected] = nextPick;
    setSpans(nextSpans);
    setHunkBody(nextBodies);
    setPicks(nextPicks);
    setDraft(nextDraft);
  }

  function onDraftChange(next: string) {
    const edit = firstEdit(draft, next);
    const nextSpans = edit
      ? shiftSpans(spans, edit.at, edit.oldLen, edit.newLen)
      : spans;
    setDraft(next);
    setSpans(nextSpans);
    setHunkBody(
      nextSpans.map((item, i) =>
        item ? next.slice(item.start, item.end) : hunkBody[i] ?? "",
      ),
    );
  }

  function jump(delta: number) {
    if (!conflictCount) return;
    setSelected((i) => Math.min(conflictCount - 1, Math.max(0, i + delta)));
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
          {conflictCount > 0 ? (
            <div className="precepts-merge-nav">
              <button
                type="button"
                className="doc-diff-btn"
                aria-label="上一处冲突"
                disabled={selected === 0}
                onClick={() => jump(-1)}
              >
                上一处
              </button>
              <span className="precepts-merge-pos" aria-live="polite">
                {selected + 1}/{conflictCount}
              </span>
              <div className="precepts-merge-jumps" role="tablist" aria-label="冲突">
                {pending.conflicts.map((item, i) => (
                  <button
                    key={`${item.ours}:${i}`}
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
                aria-label="下一处冲突"
                disabled={selected >= conflictCount - 1}
                onClick={() => jump(1)}
              >
                下一处
              </button>
            </div>
          ) : (
            <p className="precepts-merge-nav-empty">没有重叠改动，中间已是合并结果。</p>
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
            ranges={oursRanges}
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
            <textarea
              id="precepts-merge-draft"
              ref={draftRef}
              className="doc-precepts-draft precepts-merge-draft"
              value={draft}
              onChange={(e) => onDraftChange(e.target.value)}
              spellCheck={false}
            />
          </section>
          <SideDoc
            kind="theirs"
            title="官方"
            text={pending.theirs}
            ranges={theirsRanges}
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

function SideDoc({
  kind,
  title,
  text,
  ranges,
  selected,
  onSelect,
}: {
  kind: "ours" | "theirs";
  title: string;
  text: string;
  ranges: Array<{ start: number; end: number } | null>;
  selected: number;
  onSelect: (index: number) => void;
}) {
  const scroller = useRef<HTMLPreElement>(null);
  const lines = useMemo(() => (text || "").split("\n"), [text]);

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
