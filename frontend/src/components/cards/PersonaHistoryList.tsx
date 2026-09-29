import { useCallback, useEffect, useMemo, useState } from "react";
import {
  listPersonaRevisions,
  rollbackPersonaRevision,
  type PersonaRevision,
} from "../../api";
import { buildDocDiff } from "../../utils/docDiff";
import { formatMessageTime } from "../../utils/displayTime";
import { personaRevisionSourceLabel } from "./personaRevisionLabels";

type Props = {
  scope: string;
  refreshKey?: number;
  onCountChange?: (count: number | null) => void;
  onMutated?: () => void;
};

function revisionSourceLabel(revision: PersonaRevision): string {
  if (revision.source === "rollback" && revision.reverts) {
    const revertedLabel = personaRevisionSourceLabel(revision.reverts.source);
    const time = formatMessageTime(revision.reverts.created_at);
    return `回退了 ${time} 的${revertedLabel}`;
  }
  return personaRevisionSourceLabel(revision.source);
}

function PersonaRevisionDiff({
  previousBody,
  body,
}: {
  previousBody: string;
  body: string;
}) {
  const lines = useMemo(
    () => buildDocDiff(previousBody, body),
    [previousBody, body],
  );
  const hasChanges = lines.some((l) => l.type !== "unchanged");
  if (!hasChanges) {
    return <p className="persona-history-diff-empty">与上一版相同。</p>;
  }
  return (
    <pre className="doc-diff-lines persona-history-diff">
      {lines.map((line, i) => (
        <div
          key={i}
          className={`doc-diff-line doc-diff-line--${line.type}`}
        >
          <span className="doc-diff-gutter" aria-hidden>
            {line.type === "added" ? "+" : line.type === "removed" ? "−" : " "}
          </span>
          <span className="doc-diff-text">{line.content || " "}</span>
        </div>
      ))}
    </pre>
  );
}

function PersonaReasonBlock({
  reason,
  basis,
}: {
  reason: string;
  basis: string[];
}) {
  const [basisOpen, setBasisOpen] = useState(false);
  return (
    <div className="persona-history-reason-block">
      <p className="persona-history-reason-text">{reason}</p>
      {basis.length > 0 ? (
        <div className="persona-history-basis">
          <button
            type="button"
            className="card-growth-sources-toggle"
            aria-expanded={basisOpen}
            onClick={() => setBasisOpen((v) => !v)}
          >
            {basisOpen ? "收起依据" : `依据（${basis.length}）`}
          </button>
          {basisOpen ? (
            <ul className="card-growth-sources-list">
              {basis.map((text, i) => (
                <li key={i}>{text}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function PersonaRevisionRow({
  revision,
  isCurrent,
  scope,
  onRollbackSuccess,
}: {
  revision: PersonaRevision;
  isCurrent: boolean;
  scope: string;
  onRollbackSuccess: () => void;
}) {
  const [diffOpen, setDiffOpen] = useState(false);
  const [rollingBack, setRollingBack] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);

  const showReasons =
    revision.source === "evolution" && revision.reasons.length > 0;
  const canShowDiff = revision.previous_body !== "" || revision.body !== "";

  async function handleRollback() {
    if (
      !window.confirm("撤销这次改动？之后的其他改动会保留。")
    ) {
      return;
    }
    setRollingBack(true);
    setRowError(null);
    try {
      await rollbackPersonaRevision(scope, revision.id);
      onRollbackSuccess();
    } catch (err) {
      setRowError(err instanceof Error ? err.message : "回退失败");
    } finally {
      setRollingBack(false);
    }
  }

  return (
    <article className="persona-history-row">
      <header className="persona-history-row-head">
        <span className="persona-history-source">{revisionSourceLabel(revision)}</span>
        <time className="persona-history-time" dateTime={revision.created_at}>
          {formatMessageTime(revision.created_at)}
        </time>
        {isCurrent ? (
          <span className="persona-history-badge persona-history-badge--current">
            当前
          </span>
        ) : null}
        {revision.rolled_back ? (
          <span className="persona-history-badge persona-history-badge--reverted">
            已回退
          </span>
        ) : null}
      </header>

      {showReasons ? (
        <div className="persona-history-reasons">
          {revision.reasons.map((entry, index) => (
            <PersonaReasonBlock
              key={index}
              reason={entry.reason}
              basis={entry.basis}
            />
          ))}
        </div>
      ) : null}

      {canShowDiff ? (
        <div className="persona-history-diff-wrap">
          <button
            type="button"
            className="card-growth-sources-toggle"
            aria-expanded={diffOpen}
            onClick={() => setDiffOpen((v) => !v)}
          >
            {diffOpen ? "收起对照" : "对照上一版"}
          </button>
          {diffOpen ? (
            <PersonaRevisionDiff
              previousBody={revision.previous_body}
              body={revision.body}
            />
          ) : null}
        </div>
      ) : null}

      {revision.can_rollback ? (
        <div className="persona-history-actions">
          <button
            type="button"
            className="persona-history-rollback-btn"
            disabled={rollingBack}
            onClick={() => void handleRollback()}
          >
            回退
          </button>
        </div>
      ) : null}

      {rowError ? (
        <p className="persona-history-row-error">{rowError}</p>
      ) : null}
    </article>
  );
}

export function PersonaHistoryList({
  scope,
  refreshKey = 0,
  onCountChange,
  onMutated,
}: Props) {
  const [revisions, setRevisions] = useState<PersonaRevision[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listPersonaRevisions(scope);
      const next = data.revisions || [];
      setRevisions(next);
      onCountChange?.(next.length);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载人设历史失败");
      onCountChange?.(null);
    } finally {
      setLoading(false);
    }
  }, [scope, onCountChange]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const handleRollbackSuccess = useCallback(() => {
    void load();
    onMutated?.();
  }, [load, onMutated]);

  if (loading && revisions.length === 0 && !error) {
    return <p className="channel-panel-muted">加载中…</p>;
  }

  if (!loading && !error && revisions.length === 0) {
    return (
      <div className="kb-float-empty">
        <div className="kb-float-empty-mark" aria-hidden />
        <p>还没有人设修订记录。</p>
      </div>
    );
  }

  return (
    <>
      {error ? <div className="kb-float-error">错误：{error}</div> : null}
      <div className="persona-history-list">
        {revisions.map((revision, index) => (
          <PersonaRevisionRow
            key={revision.id}
            revision={revision}
            isCurrent={index === 0}
            scope={scope}
            onRollbackSuccess={handleRollbackSuccess}
          />
        ))}
      </div>
    </>
  );
}
