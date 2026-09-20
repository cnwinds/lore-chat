import { Fragment, useEffect, useMemo, useState } from "react";
import type { PreceptsUpgradePending } from "../../api";
import {
  applyHunkPick,
  changeCounts,
  exclusiveHeadings,
  foldUnchanged,
  hunkTitle,
  initialMergeDraft,
  pickedHunkText,
  sideDiff,
  type MergePick,
} from "../../utils/preceptsMergeView";
import { type DiffLine } from "../../utils/docDiff";

type Layout = "unified" | "split";

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
  const [layout, setLayout] = useState<Layout>("unified");
  const [draft, setDraft] = useState(() => initialMergeDraft(pending));
  const [picks, setPicks] = useState<MergePick[]>(() =>
    pending.conflicts.map(() => "both"),
  );
  const [hunkBody, setHunkBody] = useState<string[]>(() =>
    pending.conflicts.map((hunk) => pickedHunkText(hunk, "both")),
  );

  useEffect(() => {
    if (!open) return;
    setLayout("unified");
    setDraft(initialMergeDraft(pending));
    setPicks(pending.conflicts.map(() => "both"));
    setHunkBody(
      pending.conflicts.map((hunk) => pickedHunkText(hunk, "both")),
    );
    // pending 轮询会换新对象，同一待确认用 created_at
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, pending.created_at]);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [open, onClose]);

  const exclusive = useMemo(
    () =>
      exclusiveHeadings(
        pending.base,
        pending.ours,
        pending.theirs,
        pending.conflicts,
      ),
    [pending.base, pending.ours, pending.theirs, pending.conflicts],
  );
  const oursFile = useMemo(
    () => sideDiff(pending.base, pending.ours),
    [pending.base, pending.ours],
  );
  const theirsFile = useMemo(
    () => sideDiff(pending.base, pending.theirs),
    [pending.base, pending.theirs],
  );
  const note = exclusiveNote(exclusive);

  if (!open) return null;
  const locked = busy !== null;
  const conflictCount = pending.conflicts.length;

  function pickHunk(index: number, pick: MergePick) {
    const hunk = pending.conflicts[index];
    if (!hunk) return;
    const previous = hunkBody[index] ?? "";
    const nextDraft = applyHunkPick(draft, hunk, previous, pick);
    const nextBodies = hunkBody.slice();
    nextBodies[index] = pickedHunkText(hunk, pick);
    const nextPicks = picks.slice();
    nextPicks[index] = pick;
    setHunkBody(nextBodies);
    setPicks(nextPicks);
    setDraft(nextDraft);
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
        <header className="doc-diff-header">
          <h3 id="precepts-upgrade-title">戒律更新</h3>
          <div className="precepts-merge-header-actions">
            <div
              className="doc-toolbar-cluster doc-reading-mode"
              role="group"
              aria-label="差异版式"
            >
              <button
                type="button"
                className={`doc-reading-mode-btn${layout === "unified" ? " is-active" : ""}`}
                aria-pressed={layout === "unified"}
                onClick={() => setLayout("unified")}
              >
                合一
              </button>
              <button
                type="button"
                className={`doc-reading-mode-btn${layout === "split" ? " is-active" : ""}`}
                aria-pressed={layout === "split"}
                onClick={() => setLayout("split")}
              >
                并排
              </button>
            </div>
            <button
              type="button"
              className="doc-diff-close"
              onClick={onClose}
              aria-label="关闭"
            >
              ×
            </button>
          </div>
        </header>
        <div className="precepts-merge">
          <div className="precepts-merge-scroll">
            {note ? <p className="precepts-merge-note">{note}</p> : null}
            {conflictCount === 0 ? null : (
              pending.conflicts.map((hunk, i) => (
                <HunkCard
                  key={`${hunkTitle(hunk)}:${i}`}
                  index={i}
                  hunk={hunk}
                  layout={layout}
                  pick={picks[i] ?? "both"}
                  locked={locked}
                  onPick={(pick) => pickHunk(i, pick)}
                />
              ))
            )}
            <details className="precepts-merge-whole">
              <summary>整篇相对上次官方</summary>
              <FileDiff layout={layout} ours={oursFile} theirs={theirsFile} />
            </details>
          </div>
          <div className="precepts-merge-result">
            <label
              className="precepts-merge-result-label"
              htmlFor="precepts-merge-draft"
            >
              将写入《戒律》
              {proposing ? (
                <span className="precepts-merge-result-note">正在生成建议稿</span>
              ) : null}
            </label>
            {error ? <p className="doc-diff-empty">{error}</p> : null}
            <textarea
              id="precepts-merge-draft"
              className="doc-precepts-draft precepts-merge-draft"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              spellCheck={false}
            />
          </div>
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

function exclusiveNote(exclusive: { ours: string[]; theirs: string[] }): string {
  const auto: string[] = [];
  if (exclusive.ours.length) {
    auto.push(`现行多了「${exclusive.ours.join("」「")}」`);
  }
  if (exclusive.theirs.length) {
    auto.push(`官方多了「${exclusive.theirs.join("」「")}」`);
  }
  if (!auto.length) return "";
  return `${auto.join("，")}已放进将写入的全文。`;
}

function HunkCard({
  index,
  hunk,
  layout,
  pick,
  locked,
  onPick,
}: {
  index: number;
  hunk: PreceptsUpgradePending["conflicts"][number];
  layout: Layout;
  pick: MergePick;
  locked: boolean;
  onPick: (pick: MergePick) => void;
}) {
  const title = hunkTitle(hunk);
  const oursLines = useMemo(
    () => sideDiff(hunk.base, hunk.ours),
    [hunk.base, hunk.ours],
  );
  const theirsLines = useMemo(
    () => sideDiff(hunk.base, hunk.theirs),
    [hunk.base, hunk.theirs],
  );
  const oursCount = changeCounts(oursLines);
  const theirsCount = changeCounts(theirsLines);
  return (
    <article className="precepts-merge-hunk">
      <header className="precepts-merge-hunk-head">
        <div className="precepts-merge-hunk-meta">
          <span className="precepts-merge-hunk-at" aria-hidden>
            @@
          </span>
          <h4 className="precepts-merge-hunk-title">
            {index + 1}. {title}
          </h4>
        </div>
        <div className="precepts-merge-picks" role="group" aria-label="这块怎么收">
          <PickBtn
            label="留现行"
            pressed={pick === "ours"}
            disabled={locked}
            onClick={() => onPick("ours")}
          />
          <PickBtn
            label="用官方"
            pressed={pick === "theirs"}
            disabled={locked}
            onClick={() => onPick("theirs")}
          />
          <PickBtn
            label="两段都留"
            pressed={pick === "both"}
            disabled={locked}
            onClick={() => onPick("both")}
          />
        </div>
      </header>
      <FileDiff
        layout={layout}
        ours={oursLines}
        theirs={theirsLines}
        oursCount={oursCount}
        theirsCount={theirsCount}
        kept={pick}
      />
    </article>
  );
}

function FileDiff({
  layout,
  ours,
  theirs,
  oursCount,
  theirsCount,
  kept,
}: {
  layout: Layout;
  ours: DiffLine[];
  theirs: DiffLine[];
  oursCount?: { plus: number; minus: number };
  theirsCount?: { plus: number; minus: number };
  kept?: MergePick;
}) {
  const oursKept = kept === "ours" || kept === "both";
  const theirsKept = kept === "theirs" || kept === "both";
  if (layout === "split") {
    return (
      <div className="precepts-merge-spread">
        <DiffPane
          title="现行"
          lines={ours}
          counts={oursCount}
          kept={oursKept}
        />
        <DiffPane
          title="官方"
          lines={theirs}
          counts={theirsCount}
          kept={theirsKept}
        />
      </div>
    );
  }
  return (
    <div className="precepts-merge-stack">
      <DiffPane
        title="现行"
        lines={ours}
        counts={oursCount}
        kept={oursKept}
      />
      <DiffPane
        title="官方"
        lines={theirs}
        counts={theirsCount}
        kept={theirsKept}
      />
    </div>
  );
}

function DiffPane({
  title,
  lines,
  counts,
  kept,
}: {
  title: string;
  lines: DiffLine[];
  counts?: { plus: number; minus: number };
  kept: boolean;
}) {
  const [openFolds, setOpenFolds] = useState<Set<number>>(() => new Set());
  const rows = useMemo(() => foldUnchanged(lines), [lines]);
  return (
    <section
      className={`precepts-merge-pane${kept ? " is-kept" : ""}`}
    >
      <header className="precepts-merge-pane-head">
        <strong>{title}</strong>
        {counts ? <Counts plus={counts.plus} minus={counts.minus} /> : null}
      </header>
      <pre className="doc-diff-lines precepts-merge-lines">
        {rows.map((row) => {
          if (row.kind === "fold") {
            if (openFolds.has(row.start)) {
              return (
                <Fragment key={`open-${row.start}`}>
                  {lines.slice(row.start, row.end).map((line, j) => (
                    <DiffLineRow key={`x-${row.start}-${j}`} line={line} />
                  ))}
                </Fragment>
              );
            }
            return (
              <button
                key={`fold-${row.start}`}
                type="button"
                className="precepts-merge-fold"
                onClick={() =>
                  setOpenFolds((prev) => {
                    const next = new Set(prev);
                    next.add(row.start);
                    return next;
                  })
                }
              >
                {row.count} 行相同
              </button>
            );
          }
          return <DiffLineRow key={`l-${row.index}`} line={row.line} />;
        })}
      </pre>
    </section>
  );
}

function Counts({ plus, minus }: { plus: number; minus: number }) {
  return (
    <span className="precepts-merge-counts">
      <span className="precepts-merge-count precepts-merge-count--plus">
        +{plus}
      </span>
      <span className="precepts-merge-count precepts-merge-count--minus">
        −{minus}
      </span>
    </span>
  );
}

function PickBtn({
  label,
  pressed,
  disabled,
  onClick,
}: {
  label: string;
  pressed: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`doc-diff-btn${pressed ? " is-pressed" : ""}`}
      aria-pressed={pressed}
      onClick={onClick}
      disabled={disabled}
    >
      {label}
    </button>
  );
}

function DiffLineRow({ line }: { line: DiffLine }) {
  return (
    <div className={`doc-diff-line doc-diff-line--${line.type}`}>
      <span className="doc-diff-gutter" aria-hidden>
        {line.type === "added" ? "+" : line.type === "removed" ? "−" : " "}
      </span>
      <span className="doc-diff-text">{line.content || " "}</span>
    </div>
  );
}
