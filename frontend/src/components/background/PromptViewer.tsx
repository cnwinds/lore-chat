import { CopyButton } from "../CopyButton";
import type { BgPromptVariant } from "../../types/background";
import { countChars, splitPromptPlaceholders } from "./backgroundUtils";

type Props = {
  variant: BgPromptVariant;
};

function PromptBlock({ label, text }: { label: string; text: string }) {
  const segments = splitPromptPlaceholders(text);
  return (
    <div className="bgflow-prompt-block">
      <div className="bgflow-prompt-block-head">
        <span>{label}</span>
        <span>
          {countChars(text)} 字 · <CopyButton text={text} />
        </span>
      </div>
      <pre className="bgflow-prompt-pre">
        {segments.map((seg, i) =>
          seg.kind === "placeholder" ? (
            <mark key={i} className="bgflow-prompt-placeholder">
              {seg.value}
            </mark>
          ) : (
            <span key={i}>{seg.value}</span>
          ),
        )}
      </pre>
    </div>
  );
}

export function PromptViewer({ variant }: Props) {
  return (
    <>
      <p className="bgflow-prompt-notice" role="note">
        提示词由代码维护（AGENTS.md），此处只读。
      </p>
      {variant.notes.length > 0 ? (
        <ul className="bgflow-detail-list">
          {variant.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}
      <PromptBlock label="System" text={variant.system} />
      <PromptBlock label="User 模板" text={variant.user_template} />
    </>
  );
}
