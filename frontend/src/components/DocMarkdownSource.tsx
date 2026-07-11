import { forwardRef, useEffect, useRef } from "react";
import type { DocSelection } from "./DocLivePreview";

type Props = {
  body: string;
  onChange: (body: string, selection?: DocSelection) => void;
  readOnly?: boolean;
  selection?: DocSelection;
  onSelectionChange?: (selection: DocSelection) => void;
};

export const DocMarkdownSource = forwardRef<HTMLTextAreaElement, Props>(
  function DocMarkdownSource(
    {
      body,
      onChange,
      readOnly = false,
      selection,
      onSelectionChange,
    },
    ref,
  ) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta || selection === undefined) return;
    if (
      ta.selectionStart !== selection.start ||
      ta.selectionEnd !== selection.end
    ) {
      ta.setSelectionRange(selection.start, selection.end);
    }
  }, [selection]);

  const syncSelection = (ta: HTMLTextAreaElement) => {
    const sel = { start: ta.selectionStart, end: ta.selectionEnd };
    onSelectionChange?.(sel);
    return sel;
  };

  return (
    <textarea
      ref={(node) => {
        textareaRef.current = node;
        if (typeof ref === "function") ref(node);
        else if (ref) ref.current = node;
      }}
      className="doc-markdown-source"
      value={body}
      readOnly={readOnly}
      spellCheck={false}
      aria-label="Markdown 源码"
      onChange={(e) => {
        const ta = e.target;
        onChange(ta.value, syncSelection(ta));
      }}
      onSelect={(e) => {
        syncSelection(e.currentTarget);
      }}
      onKeyUp={(e) => {
        syncSelection(e.currentTarget);
      }}
      onClick={(e) => {
        syncSelection(e.currentTarget);
      }}
    />
  );
},
);
