import type { FormEvent } from "react";

type Props = {
  oldPassword: string;
  newPassword: string;
  confirmPassword: string;
  onOldPasswordChange: (v: string) => void;
  onNewPasswordChange: (v: string) => void;
  onConfirmPasswordChange: (v: string) => void;
  pwdError: string | null;
  pwdMsg: string | null;
  pwdSaving: boolean;
  onSubmit: (e: FormEvent) => void;
};

export function AccountSettingsTab({
  oldPassword,
  newPassword,
  confirmPassword,
  onOldPasswordChange,
  onNewPasswordChange,
  onConfirmPasswordChange,
  pwdError,
  pwdMsg,
  pwdSaving,
  onSubmit,
}: Props) {
  return (
    <div className="settings-group">
      <h3 className="settings-group-title">修改密码</h3>
      <p className="settings-group-hint">
        新密码至少 8 位。修改成功后需使用新密码登录。
      </p>
      <form className="settings-form settings-form--fields" onSubmit={onSubmit}>
        {pwdError ? <p className="settings-panel-error">{pwdError}</p> : null}
        {pwdMsg ? <p className="settings-panel-success">{pwdMsg}</p> : null}
        <label className="settings-field">
          <span>当前密码</span>
          <input
            type="password"
            autoComplete="current-password"
            value={oldPassword}
            onChange={(e) => onOldPasswordChange(e.target.value)}
            disabled={pwdSaving}
            required
          />
        </label>
        <label className="settings-field">
          <span>新密码</span>
          <input
            type="password"
            autoComplete="new-password"
            value={newPassword}
            onChange={(e) => onNewPasswordChange(e.target.value)}
            disabled={pwdSaving}
            required
            minLength={8}
          />
        </label>
        <label className="settings-field">
          <span>确认新密码</span>
          <input
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => onConfirmPasswordChange(e.target.value)}
            disabled={pwdSaving}
            required
            minLength={8}
          />
        </label>
        <footer className="settings-form-footer settings-form-footer--inline">
          <button
            type="submit"
            className="settings-btn settings-btn--primary"
            disabled={pwdSaving}
          >
            {pwdSaving ? "提交中…" : "更新密码"}
          </button>
        </footer>
      </form>
    </div>
  );
}
