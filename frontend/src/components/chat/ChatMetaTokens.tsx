import {
  compactTokenCount,
  exactTokenCount,
  type MessageTokenUsage,
} from "../../utils/chatMessageFormat";

type Way = "in" | "out";

const WAY_LABEL: Record<Way, string> = { in: "入", out: "出" };

function TokenLeg({ way, count }: { way: Way; count: number }) {
  return (
    <span className="chat-meta-token">
      <span className="chat-meta-token-way" aria-hidden>
        {WAY_LABEL[way]}
      </span>
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
