import { useMemo, type RefObject } from "react";
import type { DocContent } from "../../api";
import type { MergeReviewInfo } from "../../hooks/doc/useDocDirtyPrompt";
import type { EditMode } from "../../types/doc";
import {
  isSkillMdPath,
  joinSkillBody,
  splitSkillBodyHeader,
} from "../../utils/skillHeader";
import { DocLivePreview, type DocSelection } from "../DocLivePreview";
import { DocMarkdownSource } from "../DocMarkdownSource";
import { SkillHeaderTable } from "./SkillHeaderTable";

type Props = {
  bodyRef: RefObject<HTMLDivElement | null>;
  loading: boolean;
  error: string | null;
  saveError: string | null;
  readOnly: boolean;
  doc: DocContent | null;
  mergeReview: MergeReviewInfo | null;
  mergeEditing: boolean;
  mergeSourceRef: RefObject<HTMLTextAreaElement | null>;
  editMode: EditMode;
  body: string;
  onBodyChange: (nextBody: string, nextSelection?: DocSelection) => void;
  onPreviewChange?: (nextBody: string) => void;
  loadedPath: string;
  refreshKey: number;
  previewRemountKey: number;
  onPreviewStable: (md: string) => void;
  onPreviewUserEdit: () => void;
  markdownSourceRef: RefObject<HTMLTextAreaElement | null>;
  selection: DocSelection;
  onSelectionChange: (selection: DocSelection) => void;
};

export function DocViewerBody({
  bodyRef,
  loading,
  error,
  saveError,
  readOnly,
  doc,
  mergeReview,
  mergeEditing,
  mergeSourceRef,
  editMode,
  body,
  onBodyChange,
  onPreviewChange,
  loadedPath,
  refreshKey,
  previewRemountKey,
  onPreviewStable,
  onPreviewUserEdit,
  markdownSourceRef,
  selection,
  onSelectionChange,
}: Props) {
  const skillPreview = useMemo(() => {
    if (!isSkillMdPath(loadedPath)) return null;
    const split = splitSkillBodyHeader(body);
    // 只要匹配到 --- 头就剥离；字段可空（降级提示），禁止把 YAML 退回 Crepe
    if (!split.headerBlock) return null;
    return split;
  }, [loadedPath, body]);

  const previewBody = skillPreview?.content ?? body;
  const withSkillHeader = (content: string) =>
    joinSkillBody(skillPreview?.headerBlock, content);

  return (
    <div className="doc-viewer-body" ref={bodyRef}>
      {loading && <div className="doc-muted">加载中…</div>}
      {error && <div className="doc-error">错误：{error}</div>}
      {saveError && <div className="doc-save-error">保存失败：{saveError}</div>}
      {readOnly && doc && (
        <div className="doc-muted doc-readonly-hint">此文档为只读，无法编辑。</div>
      )}
      {doc && (
        <>
          {mergeReview && mergeEditing ? (
            <textarea
              ref={mergeSourceRef}
              className="doc-markdown-source"
              value={body}
              onChange={(e) => onBodyChange(e.target.value)}
              readOnly={readOnly}
            />
          ) : editMode === "preview" ? (
            <>
              {skillPreview && (
                <SkillHeaderTable entries={skillPreview.fields} />
              )}
              <DocLivePreview
                key={`${loadedPath}#${refreshKey}#${previewRemountKey}`}
                initialBody={previewBody}
                onChange={(b) =>
                  (onPreviewChange ?? onBodyChange)(withSkillHeader(b))
                }
                onStable={(md) => onPreviewStable(withSkillHeader(md))}
                onUserEdit={onPreviewUserEdit}
                readOnly={readOnly}
              />
            </>
          ) : (
            <DocMarkdownSource
              ref={markdownSourceRef}
              body={body}
              onChange={onBodyChange}
              readOnly={readOnly}
              selection={selection}
              onSelectionChange={onSelectionChange}
            />
          )}
        </>
      )}
    </div>
  );
}
