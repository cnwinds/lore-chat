import { useEffect, useState } from "react";
import { getQuestions, resolveQuestion, type IngestResult, type Question } from "../api";

type Props = {
  question: Question;
  conversationId?: string | null;
  resolvedLabel?: string;
  onResolved: (result: IngestResult, choiceLabel: string) => void;
};

export function PendingQuestion({
  question,
  conversationId,
  resolvedLabel,
  onResolved,
}: Props) {
  const multi =
    question.multi_select ?? /可多选|多选/.test(question.question);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [localResolved, setLocalResolved] = useState(resolvedLabel ?? "");

  useEffect(() => {
    if (resolvedLabel) {
      setLocalResolved(resolvedLabel);
      return;
    }
    let cancelled = false;
    getQuestions()
      .then(({ questions }) => {
        if (!cancelled && !questions.some((q) => q.id === question.id)) {
          setLocalResolved("已处理");
        }
      })
      .catch(() => {
        /* ignore */
      });
    return () => {
      cancelled = true;
    };
  }, [question.id, resolvedLabel]);

  function toggle(id: string) {
    setError(null);
    setSelected((prev) => {
      const next = new Set(prev);
      if (multi) {
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      }
      return new Set([id]);
    });
  }

  async function submitChoice(ids: string[], labels: string[]) {
    if (submitting || localResolved) return;
    setSubmitting(true);
    setError(null);
    const choiceLabel = labels.join("、");
    try {
      const body: {
        choice?: string;
        choices?: string[];
        conversation_id?: string;
      } = conversationId ? { conversation_id: conversationId } : {};
      if (multi && ids.length > 1) {
        body.choices = ids;
      } else {
        body.choice = ids[0];
      }
      const result = await resolveQuestion(question.id, body);
      setLocalResolved(choiceLabel);
      onResolved(result, choiceLabel);
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function submit() {
    if (selected.size === 0) return;
    const ids = Array.from(selected);
    const labels = question.options
      .filter((o) => ids.includes(o.id))
      .map((o) => o.label);
    await submitChoice(ids, labels);
  }

  async function submitSingle(id: string, label: string) {
    await submitChoice([id], [label]);
  }

  if (localResolved) {
    return (
      <div className="pending-resolved">✓ 已选择：{localResolved}</div>
    );
  }

  return (
    <div className="pending-item">
      <div className="pending-question-text">{question.question}</div>
      {multi && <div className="pending-hint">可多选，选完后点确认</div>}
      {error && <div className="pending-error">{error}</div>}
      <div className="pending-options">
        {question.options.map((o) => {
          const isSelected = selected.has(o.id);
          if (multi) {
            return (
              <label
                key={o.id}
                className={`pending-option${isSelected ? " selected" : ""}`}
              >
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => toggle(o.id)}
                  disabled={submitting}
                />
                <span>{o.label}</span>
              </label>
            );
          }
          return (
            <button
              key={o.id}
              type="button"
              className="pending-btn"
              disabled={submitting}
              onClick={() => submitSingle(o.id, o.label)}
            >
              {o.label}
            </button>
          );
        })}
      </div>
      {multi && (
        <button
          type="button"
          className="pending-confirm"
          disabled={selected.size === 0 || submitting}
          onClick={submit}
        >
          {submitting ? "提交中…" : `确认（已选 ${selected.size} 项）`}
        </button>
      )}
    </div>
  );
}
