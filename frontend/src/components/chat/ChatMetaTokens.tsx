import {
  compactTokenCount,
  exactTokenCount,
  type MessageTokenUsage,
} from "../../utils/chatMessageFormat";

type Way = "in" | "out";

function TokenWayIcon({ way }: { way: Way }) {
  return (
    <svg
      className="chat-meta-token-icon"
      viewBox="0 0 12 12"
      width="11"
      height="11"
      fill="none"
      aria-hidden
    >
      {way === "in" ? (
        <>
          <path
            d="M2.2 6h5.6"
            stroke="currentColor"
            strokeWidth="1.45"
            strokeLinecap="round"
          />
          <path
            d="M6.1 3.7 8.5 6l-2.4 2.3"
            stroke="currentColor"
            strokeWidth="1.45"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M10 3.1v5.8"
            stroke="currentColor"
            strokeWidth="1.45"
            strokeLinecap="round"
          />
        </>
      ) : (
        <>
          <path
            d="M2 3.1v5.8"
            stroke="currentColor"
            strokeWidth="1.45"
            strokeLinecap="round"
          />
          <path
            d="M3.8 6h5.6"
            stroke="currentColor"
            strokeWidth="1.45"
            strokeLinecap="round"
          />
          <path
            d="M7.5 3.7 9.9 6l-2.4 2.3"
            stroke="currentColor"
            strokeWidth="1.45"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </>
      )}
    </svg>
  );
}

function TokenLeg({ way, count }: { way: Way; count: number }) {
  return (
    <span className="chat-meta-token">
      <TokenWayIcon way={way} />
      <span className="chat-meta-token-count">{compactTokenCount(count)}</span>
    </span>
  );
}

export function ChatMetaTokens({ usage }: { usage: MessageTokenUsage }) {
  const promptExact = exactTokenCount(usage.prompt);
  const completionExact = exactTokenCount(usage.completion);
  const label = `输入 ${promptExact}，输出 ${completionExact}`;

  return (
    <span
      className="chat-meta-tokens"
      tabIndex={0}
      aria-label={label}
    >
      <TokenLeg way="in" count={usage.prompt} />
      <TokenLeg way="out" count={usage.completion} />
      <span className="chat-meta-tokens-tip" role="tooltip">
        <span className="chat-meta-tokens-tip-k">输入</span>
        <span className="chat-meta-tokens-tip-n">{promptExact}</span>
        <span className="chat-meta-tokens-tip-k">输出</span>
        <span className="chat-meta-tokens-tip-n">{completionExact}</span>
      </span>
    </span>
  );
}
