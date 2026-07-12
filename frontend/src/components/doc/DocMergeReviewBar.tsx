import { useCallback, useEffect, useState } from "react";
import { getMergeSession } from "../../api";
import type { MergeReviewInfo } from "../../hooks/doc/useDocDirtyPrompt";

type Props = {
  mergeReview: MergeReviewInfo;
  onMergeAccept?: () => void | Promise<void>;
  onMergeRegenerate?: () => void | Promise<void>;
  onMergeReject?: () => void | Promise<void>;
};

export function DocMergeReviewBar({
  mergeReview,
  onMergeAccept,
  onMergeRegenerate,
  onMergeReject,
}: Props) {
  const [mergeBusyAction, setMergeBusyAction] = useState<
    "reject" | "regenerate" | "accept" | null
  >(null);

  useEffect(() => {
    setMergeBusyAction(null);
  }, [mergeReview]);

  const ensureMergeActionConfirmed = useCallback(
    async (action: "regenerate" | "reject") => {
      const message =
        action === "regenerate"
          ? "你已修改当前合并结果。重新生成会覆盖这些修改，确定继续吗？"
          : "你已修改当前合并结果。删除此文会丢失这些修改，确定继续吗？";
      if (mergeReview.userModified) return window.confirm(message);
      try {
        const session = await getMergeSession(mergeReview.mergeId);
        if (session.user_modified) return window.confirm(message);
      } catch {
        return window.confirm("无法确认当前是否已修改，仍要继续吗？");
      }
      return true;
    },
    [mergeReview],
  );

  const runMergeAction = useCallback(
    async (action: "reject" | "regenerate" | "accept", fn?: () => void | Promise<void>) => {
      if (!fn || mergeBusyAction) return;
      setMergeBusyAction(action);
      try {
        await Promise.resolve(fn());
      } finally {
        setMergeBusyAction(null);
      }
    },
    [mergeBusyAction],
  );

  return (
    <footer className="doc-merge-review-bar">
      <span>正在审阅合并结果（源自 {mergeReview.sourcePaths.length} 篇）</span>
      <div className="doc-merge-review-actions">
        <button
          type="button"
          onClick={() =>
            void (async () => {
              if (!(await ensureMergeActionConfirmed("reject"))) return;
              await runMergeAction("reject", onMergeReject);
            })()
          }
          disabled={mergeBusyAction !== null}
        >
          删除此文
        </button>
        <button
          type="button"
          onClick={() =>
            void (async () => {
              if (!(await ensureMergeActionConfirmed("regenerate"))) return;
              await runMergeAction("regenerate", onMergeRegenerate);
            })()
          }
          disabled={mergeBusyAction !== null}
        >
          重新生成
        </button>
        <button
          type="button"
          className="doc-merge-review-accept"
          onClick={() => void runMergeAction("accept", onMergeAccept)}
          disabled={mergeBusyAction !== null}
        >
          采用
        </button>
      </div>
    </footer>
  );
}
