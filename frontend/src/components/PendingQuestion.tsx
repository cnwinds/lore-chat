import { useEffect, useRef, useState, type Ref } from "react";
import { getQuestions, resolveQuestion, type IngestResult, type Question } from "../api";
import {
  extractChoiceNote,
  formatChoiceLabel,
  optionAllowsInput,
  optionIsChosen,
} from "../utils/askUserOption";

export function sandboxRoleCaption(question: Question): string | null {
  const payload = question.payload;
  const name = typeof payload?.role_name === "string" ? payload.role_name.trim() : "";
  const id = typeof payload?.role_id === "string" ? payload.role_id.trim() : "";
  if (!name && !id) return null;
  if (name && id) return `角色：${name}（${id}）`;
  return `角色：${name || id}`;
}

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
  const sandbox = question.payload?.kind === "sandbox_confirm";
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [composingId, setComposingId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [localResolved, setLocalResolved] = useState(resolvedLabel ?? "");
  const inputRef = useRef<HTMLTextAreaElement>(null);

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

  useEffect(() => {
    if (!multi && composingId) inputRef.current?.focus();
  }, [composingId, multi]);

  function allowsInput(id: string) {
    const option = question.options.find((o) => o.id === id);
    return option ? optionAllowsInput(option, { sandbox }) : false;
  }

  function toggle(id: string) {
    setError(null);
    setSelected((prev) => {
      const next = new Set(prev);
      if (multi) {
        if (next.has(id)) {
          next.delete(id);
          setDrafts((d) => {
            const copy = { ...d };
            delete copy[id];
            return copy;
          });
        } else {
          next.add(id);
        }
        return next;
      }
      return new Set([id]);
    });
  }

  function startCompose(id: string) {
    if (submitting || localResolved) return;
    setError(null);
    setSelected(new Set([id]));
    setComposingId(id);
  }

  async function submitChoice(
    ids: string[],
    labels: string[],
    inputs?: Record<string, string>,
  ) {
    if (submitting || localResolved) return;
    setSubmitting(true);
    setError(null);
    const choiceLabel = labels.join("、");
    try {
      const body: {
        choice?: string;
        choices?: string[];
        conversation_id?: string;
        inputs?: Record<string, string>;
      } = conversationId ? { conversation_id: conversationId } : {};
      if (multi && ids.length > 1) {
        body.choices = ids;
      } else {
        body.choice = ids[0];
      }
      if (inputs && Object.keys(inputs).length > 0) {
        body.inputs = inputs;
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

  function collectInputs(ids: string[]) {
    const inputs: Record<string, string> = {};
    for (const id of ids) {
      const text = (drafts[id] || "").trim();
      if (allowsInput(id) && text) inputs[id] = text;
    }
    return inputs;
  }

  async function submitSelected() {
    if (selected.size === 0) return;
    const ids = Array.from(selected);
    const missing = ids.filter((id) => allowsInput(id) && !(drafts[id] || "").trim());
    if (missing.length) {
      setError("请写一下具体内容");
      return;
    }
    const inputs = collectInputs(ids);
    const labels = question.options
      .filter((o) => ids.includes(o.id))
      .map((o) => formatChoiceLabel(o.label, inputs[o.id]));
    await submitChoice(ids, labels, inputs);
  }

  async function submitSingle(id: string, label: string) {
    await submitChoice([id], [label]);
  }

  const roleCaption = sandboxRoleCaption(question);
  const inputMissing = Array.from(selected).some(
    (id) => allowsInput(id) && !(drafts[id] || "").trim(),
  );

  if (localResolved) {
    return (
      <div className="pending-item pending-item-resolved">
        {roleCaption ? (
          <div className="pending-role-caption">{roleCaption}</div>
        ) : null}
        <div className="pending-question-text">{question.question}</div>
        <div className="pending-resolved-note">✓ 已选择：{localResolved}</div>
        <div className="pending-options">
          {question.options.map((o) => {
            const isChosen = optionIsChosen(o.label, localResolved);
            const note = extractChoiceNote(o.label, localResolved);
            return (
              <div
                key={o.id}
                className={`pending-option-static${isChosen ? " selected" : ""}`}
              >
                <div className="pending-option-static-row">
                  <span className="pending-option-mark">{isChosen ? "●" : "○"}</span>
                  <span>{o.label}</span>
                </div>
                {note ? <div className="pending-option-note">{note}</div> : null}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div className="pending-item">
      {roleCaption ? (
        <div className="pending-role-caption">{roleCaption}</div>
      ) : null}
      <div className="pending-question-text">{question.question}</div>
      {multi && <div className="pending-hint">可多选，选完后点确认</div>}
      {error && <div className="pending-error">{error}</div>}
      <div className="pending-options">
        {question.options.map((o) => {
          const isSelected = selected.has(o.id);
          const writable = optionAllowsInput(o, { sandbox });
          if (multi && !(writable && isSelected)) {
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
          if (multi) {
            return (
              <div
                key={o.id}
                className="pending-option selected pending-option-writable"
              >
                <label className="pending-option-hit">
                  <input
                    type="checkbox"
                    checked
                    onChange={() => toggle(o.id)}
                    disabled={submitting}
                  />
                  <span>{o.label}</span>
                </label>
                <OptionCompose
                  value={drafts[o.id] || ""}
                  disabled={submitting}
                  onChange={(value) =>
                    setDrafts((prev) => ({ ...prev, [o.id]: value }))
                  }
                  onSubmit={submitSelected}
                  showSubmit={false}
                />
              </div>
            );
          }
          if (writable) {
            const isComposing = composingId === o.id;
            return (
              <div
                key={o.id}
                className={`pending-option pending-option-writable${isComposing ? " selected" : ""}`}
              >
                <button
                  type="button"
                  className="pending-option-hit"
                  disabled={submitting}
                  aria-expanded={isComposing}
                  onClick={() => startCompose(o.id)}
                >
                  <span className="pending-option-mark">{isComposing ? "●" : "○"}</span>
                  <span>{o.label}</span>
                </button>
                {isComposing ? (
                  <OptionCompose
                    value={drafts[o.id] || ""}
                    disabled={submitting}
                    inputRef={inputRef}
                    onChange={(value) =>
                      setDrafts((prev) => ({ ...prev, [o.id]: value }))
                    }
                    onSubmit={submitSelected}
                    showSubmit
                  />
                ) : null}
              </div>
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
          disabled={selected.size === 0 || submitting || inputMissing}
          onClick={submitSelected}
        >
          {submitting ? "提交中…" : `确认（已选 ${selected.size} 项）`}
        </button>
      )}
    </div>
  );
}

function autosize(el: HTMLTextAreaElement) {
  el.style.height = "0";
  el.style.height = `${el.scrollHeight}px`;
}

function OptionCompose({
  value,
  disabled,
  inputRef,
  onChange,
  onSubmit,
  showSubmit,
}: {
  value: string;
  disabled: boolean;
  inputRef?: Ref<HTMLTextAreaElement>;
  onChange: (value: string) => void;
  onSubmit: () => void;
  showSubmit: boolean;
}) {
  return (
    <div
      className="pending-option-compose"
      onClick={(event) => event.stopPropagation()}
    >
      <textarea
        ref={inputRef}
        className="pending-option-input"
        value={value}
        rows={2}
        placeholder="写下你的想法"
        aria-label="写下你的想法"
        disabled={disabled}
        onChange={(event) => {
          onChange(event.target.value);
          autosize(event.target);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            if (value.trim()) onSubmit();
          }
        }}
      />
      {showSubmit ? (
        <button
          type="button"
          className="pending-confirm pending-option-submit"
          disabled={disabled || !value.trim()}
          onClick={onSubmit}
        >
          {disabled ? "提交中…" : "确认"}
        </button>
      ) : null}
    </div>
  );
}
