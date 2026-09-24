import { useCallback, useState } from "react";
import { KbNameConflictDialog } from "../components/KbNameConflictDialog";
import type {
  KbConflictPrompt,
  KbConflictResolution,
} from "../lib/kbMutateWithConflictRetry";

type ConflictState = {
  suggestedFilename: string;
  message: string;
  existingPath?: string;
  conflictingFilename: string;
  allowOverwrite: boolean;
  filename: string;
  resolve: (choice: KbConflictResolution) => void;
};

/** 知识库/聊天上传共用的 PATH_EXISTS 弹窗。 */
export function useKbNameConflictPrompt() {
  const [conflict, setConflict] = useState<ConflictState | null>(null);

  const promptConflict = useCallback((ctx: KbConflictPrompt) => {
    setConflict({
      suggestedFilename: ctx.suggestedFilename,
      message: ctx.message,
      existingPath: ctx.existingPath,
      conflictingFilename: ctx.conflictingFilename,
      allowOverwrite: ctx.allowOverwrite ?? true,
      filename: ctx.suggestedFilename,
      resolve: ctx.resolve,
    });
  }, []);

  const conflictDialog = conflict ? (
    <KbNameConflictDialog
      open
      title="文件名已存在"
      message={conflict.message}
      existingPath={conflict.existingPath}
      conflictingFilename={conflict.conflictingFilename}
      filename={conflict.filename}
      allowOverwrite={conflict.allowOverwrite}
      onFilenameChange={(filename) =>
        setConflict((c) => (c ? { ...c, filename } : c))
      }
      onOverwrite={() => {
        conflict.resolve({ kind: "overwrite" });
        setConflict(null);
      }}
      onRename={() => {
        const name = conflict.filename.trim();
        if (!name) return;
        conflict.resolve({ kind: "rename", filename: name });
        setConflict(null);
      }}
      onCancel={() => {
        conflict.resolve({ kind: "cancel" });
        setConflict(null);
      }}
    />
  ) : null;

  return { promptConflict, conflictDialog };
}
