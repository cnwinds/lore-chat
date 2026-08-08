import type { RefObject } from "react";

type Props = {
  kbPath: string;
  backupError: string | null;
  backupMsg: string | null;
  backupBusy: boolean;
  saving: boolean;
  importFile: File | null;
  importFileRef: RefObject<HTMLInputElement | null>;
  importMode: "empty_only" | "overwrite";
  onImportFileChange: (file: File | null) => void;
  onImportModeChange: (mode: "empty_only" | "overwrite") => void;
  onExport: () => void;
  onImport: () => void;
  onReindex: () => void;
};

export function KbBackupSettingsTab({
  kbPath,
  backupError,
  backupMsg,
  backupBusy,
  saving,
  importFile,
  importFileRef,
  importMode,
  onImportFileChange,
  onImportModeChange,
  onExport,
  onImport,
  onReindex,
}: Props) {
  return (
    <>
      <div className="settings-group">
        <h3 className="settings-group-title">存储位置</h3>
        <label className="settings-field">
          <span>知识库路径（只读）</span>
          <input value={kbPath} readOnly className="settings-readonly" />
        </label>
      </div>

      {backupError ? <p className="settings-panel-error">{backupError}</p> : null}
      {backupMsg ? <p className="settings-panel-success">{backupMsg}</p> : null}

      <div className="settings-group">
        <h3 className="settings-group-title">导出</h3>
        <p className="settings-group-hint">将当前知识库打包为 zip 文件下载到本地。</p>
        <div className="settings-action-row">
          <div className="settings-action-row-text">
            <span className="settings-action-row-title">导出知识库</span>
            <span className="settings-action-row-desc">包含文档、索引与会话数据</span>
          </div>
          <button
            type="button"
            className="settings-btn settings-btn--secondary settings-btn--compact"
            onClick={onExport}
            disabled={backupBusy || saving}
          >
            {backupBusy ? "处理中…" : "导出"}
          </button>
        </div>
      </div>

      <div className="settings-group">
        <h3 className="settings-group-title">导入</h3>
        <p className="settings-group-hint">从 zip 备份包恢复知识库数据。</p>
        <div className="settings-import-block">
          <span className="settings-field-label">选择 zip 包</span>
          <input
            ref={importFileRef}
            type="file"
            accept=".zip,application/zip"
            className="settings-file-input-hidden"
            disabled={backupBusy || saving}
            onChange={(e) => onImportFileChange(e.target.files?.[0] ?? null)}
          />
          <div className="settings-file-zone-row">
            <button
              type="button"
              className={`settings-file-zone${importFile ? " settings-file-zone--selected" : ""}`}
              disabled={backupBusy || saving}
              onClick={() => importFileRef.current?.click()}
            >
              <span className="settings-file-zone-icon" aria-hidden />
              <span className="settings-file-zone-body">
                <span className="settings-file-zone-name">
                  {importFile ? importFile.name : "选择 zip 文件"}
                </span>
                <span className="settings-file-zone-hint">
                  {importFile
                    ? `${(importFile.size / 1024 / 1024).toFixed(2)} MB · 点击可重新选择`
                    : "点击选择知识库备份包"}
                </span>
              </span>
            </button>
            {importFile ? (
              <button
                type="button"
                className="settings-file-zone-clear"
                aria-label="清除已选文件"
                disabled={backupBusy || saving}
                onClick={() => {
                  onImportFileChange(null);
                  if (importFileRef.current) importFileRef.current.value = "";
                }}
              >
                ×
              </button>
            ) : null}
          </div>

          <div className="settings-option-list" role="radiogroup" aria-label="导入模式">
            <label
              className={`settings-option-card${importMode === "empty_only" ? " settings-option-card--active" : ""}`}
            >
              <input
                type="radio"
                name="import-mode"
                value="empty_only"
                className="settings-option-card-input"
                checked={importMode === "empty_only"}
                onChange={() => onImportModeChange("empty_only")}
                disabled={backupBusy || saving}
              />
              <span className="settings-option-card-title">仅空库导入</span>
              <span className="settings-option-card-desc">知识库为空时才允许导入</span>
            </label>
            <label
              className={`settings-option-card${importMode === "overwrite" ? " settings-option-card--active" : ""}`}
            >
              <input
                type="radio"
                name="import-mode"
                value="overwrite"
                className="settings-option-card-input"
                checked={importMode === "overwrite"}
                onChange={() => onImportModeChange("overwrite")}
                disabled={backupBusy || saving}
              />
              <span className="settings-option-card-title">覆盖导入</span>
              <span className="settings-option-card-desc">先自动备份，再覆盖现有数据</span>
            </label>
          </div>

          <button
            type="button"
            className="settings-btn settings-btn--primary"
            onClick={onImport}
            disabled={backupBusy || saving || !importFile}
          >
            {backupBusy ? "导入中…" : "导入知识库"}
          </button>
        </div>
      </div>

      <div className="settings-group">
        <h3 className="settings-group-title">索引维护</h3>
        <div className="settings-action-row">
          <div className="settings-action-row-text">
            <span className="settings-action-row-title">重建索引</span>
            <span className="settings-action-row-desc">文档或会话变更后，可手动重建全文与向量索引</span>
          </div>
          <button
            type="button"
            className="settings-btn settings-btn--secondary settings-btn--compact"
            onClick={onReindex}
            disabled={backupBusy || saving}
          >
            {backupBusy ? "重建中…" : "重建"}
          </button>
        </div>
      </div>
    </>
  );
}
