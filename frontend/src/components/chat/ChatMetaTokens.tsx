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
      width="12"
      height="12"
      fill="none"
      aria-hidden
    >
      {way === "in" ? (
        <>
          <path
            d="M6 1.7v6.1"
            stroke="currentColor"
            strokeWidth="1.55"
            strokeLinecap="round"
          />
          <path
            d="M3.4 5.6 6 8.2 8.6 5.6"
            stroke="currentColor"
            strokeWidth="1.55"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M2 10.4h8"
            stroke="currentColor"
            strokeWidth="1.55"
            strokeLinecap="round"
          />
        </>
      ) : (
        <>
          <path
            d="M2 1.6h8"
            stroke="currentColor"
            strokeWidth="1.55"
            strokeLinecap="round"
          />
          <path
            d="M6 4.2v6.1"
            stroke="currentColor"
            strokeWidth="1.55"
            strokeLinecap="round"
          />
          <path
            d="M3.4 6.4 6 3.8 8.6 6.4"
            stroke="currentColor"
            strokeWidth="1.55"
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
