import { useState, type FormEvent } from "react";
import { setupAuth } from "../../api";

type Props = {
  onDone: () => void;
};

const MIN_PASSWORD_LENGTH = 8;

export function SetupPage({ onDone }: Props) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`密码至少需要 ${MIN_PASSWORD_LENGTH} 位`);
      return;
    }
    if (password !== confirm) {
      setError("两次输入的密码不一致");
      return;
    }

    setSubmitting(true);
    try {
      await setupAuth(password);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "设置密码失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-gate">
      <div className="auth-gate-card">
        <h1 className="auth-gate-title">设置管理员密码</h1>
        <p className="auth-gate-subtitle">首次使用请设置登录密码，至少 8 位。</p>
        <form className="auth-gate-form" onSubmit={handleSubmit}>
          <div className="auth-gate-field">
            <label htmlFor="setup-password">密码</label>
            <input
              id="setup-password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
              required
              minLength={MIN_PASSWORD_LENGTH}
            />
          </div>
          <div className="auth-gate-field">
            <label htmlFor="setup-confirm">确认密码</label>
            <input
              id="setup-confirm"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              disabled={submitting}
              required
              minLength={MIN_PASSWORD_LENGTH}
            />
          </div>
          {error ? <p className="auth-gate-error">{error}</p> : null}
          <button type="submit" className="auth-gate-submit" disabled={submitting}>
            {submitting ? "设置中…" : "完成设置"}
          </button>
        </form>
      </div>
    </div>
  );
}
