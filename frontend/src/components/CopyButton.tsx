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
        <svg
          className="chat-copy-icon"
          viewBox="0 0 24 24"
          width="15"
          height="15"
          aria-hidden
        >
          <path
            fill="currentColor"
            d="M9.55 16.7a1.2 1.2 0 0 1-.85-.35l-3.4-3.4a1.2 1.2 0 1 1 1.7-1.7l2.55 2.55 6.45-6.45a1.2 1.2 0 1 1 1.7 1.7l-7.3 7.3a1.2 1.2 0 0 1-.85.35Z"
          />
        </svg>
      ) : (
        <svg
          className="chat-copy-icon"
          viewBox="0 0 24 24"
          width="15"
          height="15"
          aria-hidden
        >
          <rect
            x="8"
            y="2"
            width="12"
            height="14"
            rx="2.5"
            fill="currentColor"
            opacity="0.38"
          />
          <rect
            x="4"
            y="6"
            width="12"
            height="14"
            rx="2.5"
            fill="currentColor"
          />
        </svg>
      )}
    </button>
  );
}
