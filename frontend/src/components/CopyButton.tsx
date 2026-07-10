import { useState } from "react";

type Props = {
  text: string;
  className?: string;
};

export function CopyButton({ text, className }: Props) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  }

  return (
    <button
      type="button"
      className={`chat-copy-btn${className ? ` ${className}` : ""}`}
      onClick={copy}
      title={copied ? "已复制" : "复制"}
      aria-label={copied ? "已复制" : "复制"}
    >
      {copied ? (
        <span className="chat-copy-icon" aria-hidden>
          ✓
        </span>
      ) : (
        <svg
          className="chat-copy-icon"
          viewBox="0 0 16 16"
          width="14"
          height="14"
          aria-hidden
        >
          <path
            fill="currentColor"
            d="M4 2.5A1.5 1.5 0 0 1 5.5 1h5A1.5 1.5 0 0 1 12 2.5v1h.5A1.5 1.5 0 0 1 14 5v7.5A1.5 1.5 0 0 1 12.5 14h-7A1.5 1.5 0 0 1 4 12.5v-10ZM5.5 2a.5.5 0 0 0-.5.5v10a.5.5 0 0 0 .5.5h7a.5.5 0 0 0 .5-.5V5h-2.5A1.5 1.5 0 0 1 9 3.5V1h-3.5a.5.5 0 0 0-.5.5v1Z"
          />
          <path
            fill="currentColor"
            d="M10 1h1.5A1.5 1.5 0 0 1 13 2.5V11h-1V2.5a.5.5 0 0 0-.5-.5H10V1Z"
          />
        </svg>
      )}
    </button>
  );
}
