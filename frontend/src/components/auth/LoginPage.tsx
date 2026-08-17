import { useState, type FormEvent } from "react";
import { login } from "../../api";
import { LoreLogo } from "../LoreLogo";

type Props = {
  onDone: () => void;
};

const MIN_PASSWORD_LENGTH = 8;

export function LoginPage({ onDone }: Props) {
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`密码至少需要 ${MIN_PASSWORD_LENGTH} 位`);
      return;
    }

    setSubmitting(true);
    try {
      await login(password);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-gate">
      <div className="auth-gate-card">
        <LoreLogo variant="wordmark" className="auth-gate-logo" />
        <h1 className="auth-gate-title">登录</h1>
        <p className="auth-gate-subtitle">请输入管理员密码以继续使用。</p>
        <form className="auth-gate-form" onSubmit={handleSubmit}>
          <div className="auth-gate-field">
            <label htmlFor="login-password">密码</label>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
              required
              minLength={MIN_PASSWORD_LENGTH}
              autoFocus
            />
          </div>
          {error ? <p className="auth-gate-error">{error}</p> : null}
          <button type="submit" className="auth-gate-submit" disabled={submitting}>
            {submitting ? "登录中…" : "登录"}
          </button>
        </form>
      </div>
    </div>
  );
}
