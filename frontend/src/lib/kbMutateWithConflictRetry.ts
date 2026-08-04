import type { ApiError } from "../api";

export type KbConflictPrompt = {
  suggestedFilename: string;
  message: string;
  resolve: (filename: string | null) => void;
};

/**
 * 409 PATH_EXISTS 时弹窗重试，直到成功、用户取消或非冲突错误。
 */
export async function kbMutateWithConflictRetry<T>(opts: {
  initialFilename: string;
  run: (filename: string | undefined) => Promise<T>;
  onConflict: (ctx: KbConflictPrompt) => void;
  canRetryOnConflict?: (filename: string | undefined) => boolean;
}): Promise<T | null> {
  const canRetry = opts.canRetryOnConflict ?? (() => true);
  let filename: string | undefined = opts.initialFilename;

  for (;;) {
    try {
      return await opts.run(filename);
    } catch (e) {
      const err = e as ApiError;
      if (err.status === 409 && err.pathExists && canRetry(filename)) {
        const chosen = await new Promise<string | null>((resolve) => {
          opts.onConflict({
            suggestedFilename: err.pathExists!.suggested_filename,
            message: err.pathExists!.message,
            resolve,
          });
        });
        if (!chosen) return null;
        filename = chosen;
        continue;
      }
      throw e;
    }
  }
}
