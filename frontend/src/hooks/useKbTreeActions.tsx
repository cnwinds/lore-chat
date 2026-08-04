import { useCallback, useState } from "react";
import {
  kbDelete,
  kbImport,
  kbMove,
  type ApiError,
  parentDirectory,
  isMarkdownPath,
} from "../api";
import { KbNameConflictDialog } from "../components/KbNameConflictDialog";

type ConflictState = {
  file: File;
  directory: string;
  filename: string;
  message: string;
  resolve: (filename: string | null) => void;
};

export function useKbTreeActions(onTreeChanged: () => void) {
  const [conflict, setConflict] = useState<ConflictState | null>(null);
  const [busy, setBusy] = useState(false);

  const importOne = useCallback(
    async (file: File, directory: string): Promise<string | null> => {
      let filename = file.name;
      for (;;) {
        try {
          const r = await kbImport(file, directory, filename);
          return r.rel_path;
        } catch (e) {
          const err = e as ApiError;
          if (err.status === 409 && err.pathExists) {
            const chosen = await new Promise<string | null>((resolve) => {
              setConflict({
                file,
                directory,
                filename: err.pathExists!.suggested_filename,
                message: err.pathExists!.message,
                resolve,
              });
            });
            setConflict(null);
            if (!chosen) return null;
            filename = chosen;
            continue;
          }
          throw e;
        }
      }
    },
    [],
  );

  const importMany = useCallback(
    async (files: FileList | File[], directory: string) => {
      setBusy(true);
      try {
        for (const file of Array.from(files)) {
          await importOne(file, directory);
        }
        onTreeChanged();
      } finally {
        setBusy(false);
      }
    },
    [importOne, onTreeChanged],
  );

  const moveFile = useCallback(
    async (fromPath: string, toDirectory: string, toFilename?: string) => {
      setBusy(true);
      try {
        let name = toFilename;
        for (;;) {
          try {
            const r = await kbMove({
              from_path: fromPath,
              to_directory: toDirectory,
              to_filename: name,
            });
            onTreeChanged();
            return r.rel_path;
          } catch (e) {
            const err = e as ApiError;
            if (err.status === 409 && err.pathExists && name !== undefined) {
              const chosen = await new Promise<string | null>((resolve) => {
                setConflict({
                  file: new File([], name || fromPath.split("/").pop() || "file"),
                  directory: toDirectory,
                  filename: err.pathExists!.suggested_filename,
                  message: err.pathExists!.message,
                  resolve,
                });
              });
              setConflict(null);
              if (!chosen) return null;
              name = chosen;
              continue;
            }
            throw e;
          }
        }
      } finally {
        setBusy(false);
      }
    },
    [onTreeChanged],
  );

  const renameFile = useCallback(
    async (fromPath: string, newFilename: string) => {
      const contentDir = (() => {
        const norm = fromPath.replace(/\\/g, "/");
        const i = norm.indexOf("/attachments/");
        if (i === -1) return parentDirectory(norm);
        return norm.slice(0, i);
      })();
      if (isMarkdownPath(fromPath)) {
        return moveFile(fromPath, parentDirectory(fromPath), newFilename);
      }
      return moveFile(fromPath, contentDir, newFilename);
    },
    [moveFile],
  );

  const deletePath = useCallback(
    async (path: string): Promise<string[]> => {
      setBusy(true);
      try {
        const r = await kbDelete(path);
        onTreeChanged();
        return r.deleted_paths;
      } finally {
        setBusy(false);
      }
    },
    [onTreeChanged],
  );

  const conflictDialog = conflict ? (
    <KbNameConflictDialog
      open
      title="名称已存在"
      message={conflict.message}
      filename={conflict.filename}
      onFilenameChange={(filename) =>
        setConflict((c) => (c ? { ...c, filename } : c))
      }
      onConfirm={() => conflict.resolve(conflict.filename)}
      onCancel={() => conflict.resolve(null)}
    />
  ) : null;

  return {
    busy,
    conflictDialog,
    importMany,
    moveFile,
    renameFile,
    deletePath,
  };
}
