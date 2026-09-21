import { MergeTool } from "../merge3/MergeTool";

type Props = {
  older: string;
  newer: string;
  olderLabel?: string;
  newerLabel?: string;
};

/**
 * 修订历史的三栏对照：上一版既是左栏也是共同基线，所有差异都是
 * 「这一版」的可摘取块，中间结果默认等于这一版，可逐块回退。
 */
export function DocRevisionCompareView({
  older,
  newer,
  olderLabel = "上一版",
  newerLabel = "这一版",
}: Props) {
  return (
    <div className="doc-revision-compare">
      <MergeTool
        base={older}
        ours={older}
        theirs={newer}
        oursTitle={olderLabel}
        theirsTitle={newerLabel}
        className="merge3--history"
      />
    </div>
  );
}
