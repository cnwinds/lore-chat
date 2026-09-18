import { useEffect, useState } from "react";
import type { PackPathChoiceDetail } from "../lib/httpTransport";

type Props = {
  open: boolean;
  detail: PackPathChoiceDetail;
  onConfirm: (path: string) => void;
  onCancel: () => void;
};

export function PackPathChoiceDialog({
  open,
  detail,
  onConfirm,
  onCancel,
}: Props) {
  const defaultPath = detail.default_path || detail.upload_path;
  const [selected, setSelected] = useState(defaultPath);

  useEffect(() => {
    setSelected(detail.default_path || detail.upload_path);
  }, [detail]);

  if (!open) return null;

  const options: { path: string; label: string; note?: string }[] = [
    {
      path: detail.upload_path,
      label: "当前拖入的位置（默认）",
      note:
        detail.kind === "skill" && detail.upload_outside_skills
          ? `Skill 包必须放在「${detail.skills_dir || "技能"}」目录下，选这里将无法作为技能导入。`
          : undefined,
    },
    {
      path: detail.original_path,
      label: "原来的位置",
    },
  ];

  return (
    <div className="modal-backdrop" role="presentation" onClick={onCancel}>
      <div
        className="modal-panel kb-conflict-dialog kb-pack-choice-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pack-path-choice-title"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Enter") onConfirm(selected);
          if (e.key === "Escape") onCancel();
        }}
      >
        <h3 id="pack-path-choice-title">解压到哪个路径？</h3>
        <p className="kb-conflict-message">{detail.message}</p>
        <div className="kb-pack-choice-list" role="radiogroup" aria-labelledby="pack-path-choice-title">
          {options.map((opt, index) => {
            const id = `pack-path-${index}`;
            return (
              <label
                key={opt.label}
                className="kb-pack-choice-item"
                data-selected={selected === opt.path ? "true" : "false"}
                htmlFor={id}
              >
                <input
                  id={id}
                  type="radio"
                  name="pack-path-choice"
                  value={opt.path}
                  checked={selected === opt.path}
                  onChange={() => setSelected(opt.path)}
                />
                <span>
                  <span className="kb-pack-choice-label">{opt.label}</span>
                  <span className="kb-pack-choice-path">{opt.path || "根目录"}</span>
                  {opt.note ? (
                    <span className="kb-pack-choice-note">{opt.note}</span>
                  ) : null}
                </span>
              </label>
            );
          })}
        </div>
        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>
            取消
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={() => onConfirm(selected)}
            autoFocus
          >
            解压到所选路径
          </button>
        </div>
      </div>
    </div>
  );
}
