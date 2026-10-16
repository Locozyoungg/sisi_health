import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setToken } from "../api";

interface LoginResponse {
  access_token: string;
  role: string;
}

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const data = await api<LoginResponse>("/v1/staff/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password, totp_code: totp }),
      });
      setToken(data.access_token);
      navigate("/queue");
    } catch (err) {
      setError(err instanceof Error ? err.message : "login failed");
    }
  }

  return (
    <main className="login-shell">
      <div className="card login-card">
        <div className="login-brand">
          <span className="brand-mark" aria-hidden="true" />
          <h1 className="login-title">SISI Health Console</h1>
        </div>
        <p className="login-tagline muted">SISI supports you and your doctor — it does not diagnose.</p>
        <form className="form-grid login-form" onSubmit={onSubmit}>
          <label className="form-field">
            Email
            <input
              className="input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
            />
          </label>
          <label className="form-field">
            Password
            <input
              className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </label>
          <label className="form-field">
            TOTP code
            <input
              className="input"
              value={totp}
              onChange={(e) => setTotp(e.target.value)}
              inputMode="numeric"
              maxLength={6}
              autoComplete="one-time-code"
            />
          </label>
          <button type="submit" className="btn btn-primary btn-block">
            Sign in
          </button>
          {error && (
            <p className="alert alert-danger" role="alert">
              {error}
            </p>
          )}
        </form>
        <p className="login-note muted">Staff access only — sessions lock after 15 minutes idle.</p>
      </div>
    </main>
  );
}
