import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import {
  acceptMerge,
  getActiveMerge,
  regenerateMerge,
  rejectMerge,
} from "../../api";
import type { RefreshKb } from "../../types/doc";

export type MergeReviewState = {
  mergeId: string;
  newPath: string;
  sourcePaths: string[];
  userModified: boolean;
} | null;

export type MergeSourceQuestionState = {
  mergeId: string;
  newPath: string;
  sourcePaths: string[];
  questionId?: string;
} | null;

type UseMergeReviewSessionOptions = {
  previewPath: string | null;
  openDocPreview: (
    path: string,
    excerpt?: string,
    options?: { pin?: boolean },
  ) => void;
  closeDocPreview: () => void;
  refreshKb: RefreshKb;
  setDocRefreshKey: Dispatch<SetStateAction<number>>;
  setSelectionMode: Dispatch<SetStateAction<boolean>>;
  clearSelection: () => void;
};

export function useMergeReviewSession({
  previewPath,
  openDocPreview,
  closeDocPreview,
  refreshKb,
  setDocRefreshKey,
  setSelectionMode,
  clearSelection,
}: UseMergeReviewSessionOptions) {
  const [mergeReview, setMergeReview] = useState<MergeReviewState>(null);
  const [mergeSourceQuestion, setMergeSourceQuestion] =
    useState<MergeSourceQuestionState>(null);

  useEffect(() => {
    if (!previewPath) {
      setMergeReview(null);
      return;
    }
    let cancelled = false;
    void getActiveMerge(previewPath)
      .then((session) => {
        if (cancelled) return;
        if (!session || session.status !== "pending_review") {
          setMergeReview((prev) => (prev?.newPath === previewPath ? null : prev));
          return;
        }
        setMergeReview({
          mergeId: session.id,
          newPath: session.new_path,
          sourcePaths: session.source_paths,
          userModified: session.user_modified,
        });
      })
      .catch(() => {
        if (!cancelled) {
          setMergeReview((prev) => (prev?.newPath === previewPath ? null : prev));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [previewPath]);

  function handleMergeComplete(result: {
    merge_id: string | null;
    rel_path: string | null;
    source_paths: string[];
    user_modified: boolean;
  }) {
    if (!result.merge_id || !result.rel_path) return;
    openDocPreview(result.rel_path, undefined, { pin: true });
    setMergeReview({
      mergeId: result.merge_id,
      newPath: result.rel_path,
      sourcePaths: result.source_paths,
      userModified: result.user_modified,
    });
    setMergeSourceQuestion(null);
    refreshKb();
    setSelectionMode(false);
    clearSelection();
  }

  async function handleMergeAccept() {
    if (!mergeReview) return;
    const current = mergeReview;
    try {
      const result = await acceptMerge(current.mergeId);
      setMergeReview(null);
      refreshKb(current.newPath);
      if (result.question_id) {
        setMergeSourceQuestion({
          mergeId: current.mergeId,
          newPath: current.newPath,
          sourcePaths: current.sourcePaths,
          questionId: result.question_id,
        });
      } else {
        setMergeSourceQuestion(null);
      }
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "采用失败");
    }
  }

  async function handleMergeRegenerate() {
    if (!mergeReview) return;
    try {
      const result = await regenerateMerge(mergeReview.mergeId);
      setMergeReview((prev) =>
        prev
          ? {
              ...prev,
              sourcePaths:
                result.source_paths.length > 0
                  ? result.source_paths
                  : prev.sourcePaths,
              userModified: false,
            }
          : prev,
      );
      setDocRefreshKey((k) => k + 1);
      refreshKb(mergeReview.newPath);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "重新生成失败");
    }
  }

  async function handleMergeReject() {
    if (!mergeReview) return;
    try {
      await rejectMerge(mergeReview.mergeId);
      closeDocPreview();
      setMergeReview(null);
      setMergeSourceQuestion(null);
      refreshKb();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "删除失败");
    }
  }

  const activeMergeReview =
    mergeReview && previewPath === mergeReview.newPath
      ? {
          mergeId: mergeReview.mergeId,
          sourcePaths: mergeReview.sourcePaths,
          userModified: mergeReview.userModified,
        }
      : null;

  return {
    mergeReview,
    setMergeReview,
    mergeSourceQuestion,
    setMergeSourceQuestion,
    activeMergeReview,
    handleMergeAccept,
    handleMergeRegenerate,
    handleMergeReject,
    handleMergeComplete,
  };
}
