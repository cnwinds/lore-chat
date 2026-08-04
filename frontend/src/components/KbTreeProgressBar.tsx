import type { KbTreeProgress } from "../hooks/useKbTreeActions";

type Props = {
  progress: KbTreeProgress;
};

export function KbTreeProgressBar({ progress }: Props) {
  const pct = Math.min(
    100,
    Math.round(((progress.completed + 1) / progress.total) * 100),
  );
  const verb = progress.kind === "import" ? "上传" : "移动";

  return (
    <div className="kb-import-progress" role="status" aria-live="polite">
      <div className="kb-import-progress-text">
        正在{verb} {progress.completed + 1}/{progress.total}
        {progress.currentName ? ` · ${progress.currentName}` : ""}
      </div>
      <div className="kb-import-progress-bar" aria-hidden>
        <div className="kb-import-progress-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
