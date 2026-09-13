import { useEffect, useMemo, useState, type KeyboardEvent, type RefObject } from "react";
import {
  filterMentionRoles,
  mentionQueryAtCaret,
  type MentionCandidate,
} from "../../utils/roleMentions";
import { mentionOptionId } from "../../components/chat/mentionPickerIds";

type Args = {
  input: string;
  caret: number;
  setInput: (value: string) => void;
  setCaret: (value: number) => void;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
  candidates: MentionCandidate[];
};

export function useMentionPicker({
  input,
  caret,
  setInput,
  setCaret,
  textareaRef,
  candidates,
}: Args) {
  const mention = mentionQueryAtCaret(input, caret);
  const [closed, setClosed] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);

  const mentionStart = mention?.start;
  const mentionQuery = mention?.query ?? "";
  const hits = useMemo(() => {
    if (mentionStart == null) return [];
    return filterMentionRoles(candidates, mentionQuery);
  }, [candidates, mentionStart, mentionQuery]);

  useEffect(() => {
    setClosed(false);
    setSelectedIndex(0);
  }, [mention?.start, mention?.query]);

  useEffect(() => {
    if (selectedIndex >= hits.length) {
      setSelectedIndex(0);
    }
  }, [hits.length, selectedIndex]);

  const open = Boolean(mention) && !closed;
  const active = open && hits.length ? hits[selectedIndex] ?? hits[0] : null;

  function apply(role: MentionCandidate) {
    if (!mention) return;
    const insert = `@${role.name} `;
    const next = `${input.slice(0, mention.start)}${insert}${input.slice(caret)}`;
    const nextCaret = mention.start + insert.length;
    setInput(next);
    setCaret(nextCaret);
    setClosed(true);
    requestAnimationFrame(() => {
      const el = textareaRef.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(nextCaret, nextCaret);
    });
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>): boolean {
    if (!open) return false;
    if (e.nativeEvent.isComposing) return false;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (hits.length) {
        setSelectedIndex((i) => (i + 1) % hits.length);
      }
      return true;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      if (hits.length) {
        setSelectedIndex((i) => (i - 1 + hits.length) % hits.length);
      }
      return true;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      setClosed(true);
      return true;
    }
    if ((e.key === "Enter" || e.key === "Tab") && !e.shiftKey && active) {
      e.preventDefault();
      apply(active);
      return true;
    }
    return false;
  }

  return {
    mention,
    hits,
    open,
    selectedIndex,
    setSelectedIndex,
    apply,
    handleKeyDown,
    activeOptionId: active ? mentionOptionId(active.id) : undefined,
  };
}
