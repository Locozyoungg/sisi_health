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
    <main style={{ maxWidth: 420, margin: "80px auto", padding: 24 }}>
      <h1>SISI Health Console</h1>
      <p>SISI supports you and your doctor — it does not diagnose.</p>
      <form onSubmit={onSubmit} style={{ display: "grid", gap: 12 }}>
        <label>
          Email
          <input value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>
        <label>
          TOTP code
          <input
            value={totp}
            onChange={(e) => setTotp(e.target.value)}
            inputMode="numeric"
            maxLength={6}
            autoComplete="one-time-code"
          />
        </label>
        <button type="submit">Sign in</button>
        {error && <p role="alert">{error}</p>}
      </form>
    </main>
  );
}
