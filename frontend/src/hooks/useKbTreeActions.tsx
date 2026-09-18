import { useCallback, useState } from "react";
import {
  kbDelete,
  kbImport,
  kbMove,
  parentDirectory,
} from "../api";
import type { ApiError, PackPathChoiceDetail } from "../api";
import { KbNameConflictDialog } from "../components/KbNameConflictDialog";
import { PackPathChoiceDialog } from "../components/PackPathChoiceDialog";
import { kbMutateWithConflictRetry } from "../lib/kbMutateWithConflictRetry";
import {
  targetDirectoryForDrop,
  type DroppedFile,
} from "../utils/droppedFiles";
import { isKbDirectoryPath } from "../utils/kbTreeMove";

type ConflictState = {
  filename: string;
  message: string;
  resolve: (filename: string | null) => void;
};

type PackChoiceState = {
  detail: PackPathChoiceDetail;
  resolve: (path: string | null) => void;
};

export type KbTreeProgress = {
  kind: "import" | "move";
  total: number;
  completed: number;
  currentName: string;
};

function zipStem(filename: string): string {
  const base = filename.replace(/\\/g, "/").split("/").pop() ?? filename;
  return base.replace(/\.zip$/i, "").trim() || base;
}

function replacePathLeaf(path: string, leaf: string): string {
  const parts = path.split("/").filter(Boolean);
  if (!parts.length) return leaf;
  parts[parts.length - 1] = leaf;
  return parts.join("/");
}

export function useKbTreeActions(onTreeChanged: () => void, docs: string[]) {
  const [conflict, setConflict] = useState<ConflictState | null>(null);
  const [packChoice, setPackChoice] = useState<PackChoiceState | null>(null);
  const [busy, setBusy] = useState(false);
  const [treeProgress, setTreeProgress] = useState<KbTreeProgress | null>(null);

  const promptConflict = useCallback((ctx: {
    suggestedFilename: string;
    message: string;
    resolve: (filename: string | null) => void;
  }) => {
    setConflict({
      filename: ctx.suggestedFilename,
      message: ctx.message,
      resolve: ctx.resolve,
    });
  }, []);

  const promptPackPath = useCallback((detail: PackPathChoiceDetail) => {
    return new Promise<string | null>((resolve) => {
      setPackChoice({ detail, resolve });
    });
  }, []);

  const importOne = useCallback(
    async (
      file: File,
      directory: string,
      filename?: string,
    ): Promise<string | null> => {
      const initialFilename = filename ?? file.name;
      const runImport = (targetDir: string, destRoot?: string) => {
        let currentDest = destRoot;
        return kbMutateWithConflictRetry({
          initialFilename,
          onConflict: (ctx) => {
            promptConflict({
              suggestedFilename: ctx.suggestedFilename,
              message: ctx.message,
              resolve: (name) => {
                if (name && currentDest) {
                  currentDest = replacePathLeaf(currentDest, zipStem(name));
                }
                ctx.resolve(name);
              },
            });
          },
          run: async (name) => {
            const r = await kbImport(file, targetDir, name!, currentDest);
            return r.rel_path;
          },
        });
      };
      try {
        const rel = await runImport(directory);
        setConflict(null);
        return rel;
      } catch (e) {
        const err = e as ApiError;
        if (err.status === 409 && err.packPathChoice) {
          const chosen = await promptPackPath(err.packPathChoice);
          setPackChoice(null);
          if (!chosen) return null;
          const rel = await runImport(directory, chosen);
          setConflict(null);
          return rel;
        }
        throw e;
      }
    },
    [promptConflict, promptPackPath],
  );

  const importMany = useCallback(
    async (items: DroppedFile[], directory: string) => {
      setBusy(true);
      setTreeProgress({
        kind: "import",
        total: items.length,
        completed: 0,
        currentName: items[0]?.relativePath ?? "",
      });
      try {
        for (let i = 0; i < items.length; i++) {
          const { file, relativePath } = items[i];
          const target = targetDirectoryForDrop(directory, relativePath);
          setTreeProgress({
            kind: "import",
            total: items.length,
            completed: i,
            currentName: relativePath,
          });
          await importOne(file, target.directory, target.filename);
        }
        onTreeChanged();
      } catch (e) {
        const msg = e instanceof Error ? e.message : "导入失败";
        window.alert(msg);
        onTreeChanged();
      } finally {
        setTreeProgress(null);
        setBusy(false);
      }
    },
    [importOne, onTreeChanged],
  );

  const moveOneEntry = useCallback(
    async (
      fromPath: string,
      toDirectory: string,
      toFilename: string,
    ): Promise<string | null> => {
      const rel = await kbMutateWithConflictRetry({
        initialFilename: toFilename,
        canRetryOnConflict: (name) => name !== undefined,
        onConflict: promptConflict,
        run: async (name) => {
          const r = await kbMove({
            from_path: fromPath,
            to_directory: toDirectory,
            to_filename: name,
          });
          return r.rel_path;
        },
      });
      setConflict(null);
      return rel;
    },
    [promptConflict],
  );

  const moveFile = useCallback(
    async (fromPath: string, toDirectory: string, toFilename?: string) => {
      const folderName = toFilename ?? fromPath.split("/").pop() ?? "file";

      setBusy(true);
      setTreeProgress({
        kind: "move",
        total: 1,
        completed: 0,
        currentName: fromPath,
      });
      try {
        const rel = await moveOneEntry(fromPath, toDirectory, folderName);
        onTreeChanged();
        return rel;
      } catch (e) {
        const msg = e instanceof Error ? e.message : "移动失败";
        window.alert(msg);
        onTreeChanged();
        return null;
      } finally {
        setTreeProgress(null);
        setBusy(false);
      }
    },
    [moveOneEntry, onTreeChanged],
  );

  const renameFile = useCallback(
    async (fromPath: string, newFilename: string) => {
      return moveFile(fromPath, parentDirectory(fromPath), newFilename);
    },
    [moveFile],
  );

  const renameEntry = useCallback(
    async (fromPath: string, newName: string) => {
      const trimmed = newName.trim();
      if (!trimmed) return null;
      if (isKbDirectoryPath(fromPath, docs)) {
        return moveFile(fromPath, parentDirectory(fromPath), trimmed);
      }
      return renameFile(fromPath, trimmed);
    },
    [docs, moveFile, renameFile],
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

  const conflictDialog = (
    <>
      {conflict ? (
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
      ) : null}
      {packChoice ? (
        <PackPathChoiceDialog
          open
          detail={packChoice.detail}
          onConfirm={(path) => packChoice.resolve(path)}
          onCancel={() => packChoice.resolve(null)}
        />
      ) : null}
    </>
  );

  return {
    busy,
    treeProgress,
    conflictDialog,
    importMany,
    moveFile,
    renameFile,
    renameEntry,
    deletePath,
  };
}
