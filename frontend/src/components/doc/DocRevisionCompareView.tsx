import { useEffect, useMemo, useRef, useState } from "react";
import {
  buildRevisionMergeModel,
  revisionDiffSummary,
  sideLineTonesForRevision,
  type SideLineTone,
} from "../../utils/docRevisionMergeView";
import {
  applyHunkPick,
  firstEdit,
  hunkIndexAtLine,
  hunkTitle,
  lineRange,
  locateHunkSpans,
  pickedHunkText,
  replaceSpan,
  shiftSpans,
  type HunkSpan,
  type MergePick,
} from "../../utils/preceptsMergeView";

type Props = {
  older: string;
  newer: string;
  olderLabel?: string;
  newerLabel?: string;
};

export function DocRevisionCompareView({
  older,
  newer,
  olderLabel = "上一版",
  newerLabel = "这一版",
}: Props) {
  const model = useMemo(
    () => buildRevisionMergeModel(older, newer),
    [older, newer],
  );
  const summary = useMemo(
    () => revisionDiffSummary(older, newer),
    [older, newer],
  );
  const tones = useMemo(
    () => sideLineTonesForRevision(older, newer, model.conflicts),
    [older, newer, model.conflicts],
  );

  const [selected, setSelected] = useState(0);
  const [draft, setDraft] = useState(model.draft);
  const [picks, setPicks] = useState<MergePick[]>(() =>
    model.conflicts.map(() => "theirs"),
  );
  const [hunkBody, setHunkBody] = useState<string[]>(() =>
    model.conflicts.map((hunk) => pickedHunkText(hunk, "theirs")),
  );
  const [spans, setSpans] = useState<Array<HunkSpan | null>>(() =>
    locateHunkSpans(
      model.draft,
      model.conflicts.map((hunk) => pickedHunkText(hunk, "theirs")),
    ),
  );
  const draftRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const next = buildRevisionMergeModel(older, newer);
    const bodies = next.conflicts.map((hunk) => pickedHunkText(hunk, "theirs"));
    setSelected(0);
    setDraft(next.draft);
    setPicks(next.conflicts.map(() => "theirs"));
    setHunkBody(bodies);
    setSpans(locateHunkSpans(next.draft, bodies));
  }, [older, newer]);

  useEffect(() => {
    const el = draftRef.current;
    const span = spans[selected];
    if (!el || !span) return;
    const lh = Number.parseFloat(getComputedStyle(el).lineHeight) || 20;
    const line = el.value.slice(0, span.start).split("\n").length;
    el.scrollTop = Math.max(0, (line - 3) * lh);
  }, [selected, spans]);

  const olderRanges = useMemo(
    () => model.conflicts.map((hunk) => lineRange(older, hunk.ours)),
    [model.conflicts, older],
  );
  const newerRanges = useMemo(
    () => model.conflicts.map((hunk) => lineRange(newer, hunk.theirs)),
    [model.conflicts, newer],
  );

  const conflictCount = model.conflicts.length;
  const hunk = model.conflicts[selected];
  const pick = picks[selected] ?? "theirs";

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
    <div className="doc-revision-compare">
      <div className="doc-revision-compare-bar">
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
              {model.conflicts.map((item, i) => (
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
          <p className="precepts-merge-nav-empty">
            没有重叠改动，中间已是自动合并结果。
          </p>
        )}
        <span className="doc-revision-compare-stats" aria-live="polite">
          {summary.changes} 处改动
          {summary.conflicts > 0 ? `，${summary.conflicts} 处冲突` : ""}
        </span>
      </div>
      <div className="precepts-merge-triple">
        <SideDoc
          kind="ours"
          title={olderLabel}
          text={older}
          ranges={olderRanges}
          tones={tones.older}
          selected={selected}
          onSelect={setSelected}
        />
        <section className="precepts-merge-col precepts-merge-col--result">
          <header className="precepts-merge-col-head">
            <label htmlFor="doc-revision-merge-draft">
              结果
              {hunk ? (
                <span className="precepts-merge-result-note">{hunkTitle(hunk)}</span>
              ) : null}
            </label>
            {hunk ? (
              <div className="precepts-merge-picks" role="group" aria-label="这块怎么收">
                <PickBtn
                  label="用上一版"
                  tone="ours"
                  pressed={pick === "ours"}
                  onClick={() => pickHunk("ours")}
                />
                <PickBtn
                  label="两边都留"
                  tone="both"
                  pressed={pick === "both"}
                  onClick={() => pickHunk("both")}
                />
                <PickBtn
                  label="用这一版"
                  tone="theirs"
                  pressed={pick === "theirs"}
                  onClick={() => pickHunk("theirs")}
                />
              </div>
            ) : null}
          </header>
          <textarea
            id="doc-revision-merge-draft"
            ref={draftRef}
            className="doc-precepts-draft precepts-merge-draft"
            value={draft}
            onChange={(e) => onDraftChange(e.target.value)}
            spellCheck={false}
          />
        </section>
        <SideDoc
          kind="theirs"
          title={newerLabel}
          text={newer}
          ranges={newerRanges}
          tones={tones.newer}
          selected={selected}
          onSelect={setSelected}
        />
      </div>
    </div>
  );
}

function SideDoc({
  kind,
  title,
  text,
  ranges,
  tones,
  selected,
  onSelect,
}: {
  kind: "ours" | "theirs";
  title: string;
  text: string;
  ranges: Array<{ start: number; end: number } | null>;
  tones: SideLineTone[];
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
          const tone = tones[i] ?? "plain";
          return (
            <div
              key={i}
              data-active-conflict={active ? "" : undefined}
              role={hit >= 0 ? "button" : undefined}
              tabIndex={hit >= 0 ? 0 : undefined}
              className={lineClass(kind, hit, active, tone)}
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

function lineClass(
  kind: "ours" | "theirs",
  hit: number,
  active: boolean,
  tone: SideLineTone,
): string {
  const parts = ["precepts-merge-doc-line"];
  if (hit >= 0) parts.push("is-conflict");
  else if (tone === "change") parts.push("is-change");
  if (active) parts.push("is-active");
  if (tone === "conflict" && hit < 0) parts.push("is-conflict");
  if (kind === "theirs" && tone === "change") parts.push("is-change-theirs");
  if (kind === "ours" && tone === "change") parts.push("is-change-ours");
  return parts.join(" ");
}

function PickBtn({
  label,
  tone,
  pressed,
  onClick,
}: {
  label: string;
  tone: MergePick;
  pressed: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`doc-diff-btn precepts-merge-pick precepts-merge-pick--${tone}${pressed ? " is-pressed" : ""}`}
      aria-pressed={pressed}
      onClick={onClick}
    >
      {label}
    </button>
  );
}
