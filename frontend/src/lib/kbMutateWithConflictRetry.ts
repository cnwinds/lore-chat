import type { ApiError } from "../api";

export type KbConflictResolution =
  | { kind: "cancel" }
  | { kind: "overwrite" }
  | { kind: "rename"; filename: string };

export type KbConflictPrompt = {
  suggestedFilename: string;
  message: string;
  existingPath?: string;
  /** 本次冲突使用的文件名（覆盖时沿用） */
  conflictingFilename: string;
  allowOverwrite?: boolean;
  resolve: (choice: KbConflictResolution) => void;
};

export type KbMutateRunOptions = {
  filename: string | undefined;
  overwrite: boolean;
};

/**
 * 409 PATH_EXISTS 时弹窗重试，直到成功、用户取消或非冲突错误。
 */
export async function kbMutateWithConflictRetry<T>(opts: {
  initialFilename: string;
  run: (ctx: KbMutateRunOptions) => Promise<T>;
  onConflict: (ctx: KbConflictPrompt) => void;
  canRetryOnConflict?: (ctx: KbMutateRunOptions) => boolean;
  /** 移动/重命名等场景不允许覆盖，仅换名 */
  allowOverwrite?: boolean;
}): Promise<T | null> {
  const canRetry = opts.canRetryOnConflict ?? (() => true);
  let filename: string | undefined = opts.initialFilename;
  let overwrite = false;

  for (;;) {
    try {
      return await opts.run({ filename, overwrite });
    } catch (e) {
      const err = e as ApiError;
      const ctx: KbMutateRunOptions = { filename, overwrite };
      if (err.status === 409 && err.pathExists && canRetry(ctx)) {
        const choice = await new Promise<KbConflictResolution>((resolve) => {
          opts.onConflict({
            suggestedFilename: err.pathExists!.suggested_filename,
            message: err.pathExists!.message,
            existingPath: err.pathExists!.path,
            conflictingFilename: filename ?? opts.initialFilename,
            allowOverwrite: opts.allowOverwrite ?? true,
            resolve,
          });
        });
        if (choice.kind === "cancel") return null;
        if (choice.kind === "overwrite") {
          if (!(opts.allowOverwrite ?? true)) {
            throw new Error("此操作不支持覆盖已有文件");
          }
          overwrite = true;
          filename = filename ?? opts.initialFilename;
          continue;
        }
        overwrite = false;
        filename = choice.filename;
        continue;
      }
      throw e;
    }
  }
}
