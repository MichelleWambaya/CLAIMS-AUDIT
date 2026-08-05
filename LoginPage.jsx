import React, { useState } from "react";
import { api } from "../lib/api";

export default function LoginPage({ onLoggedIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const result = await api.login(email, password);
      if (!result.access_token) {
        throw new Error(result.detail || "Login failed");
      }
      localStorage.setItem("aar_token", result.access_token);
      localStorage.setItem("aar_role", result.role);
      onLoggedIn();
    } catch (err) {
      setError("Incorrect email or password.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "center",
      minHeight: "100vh", background: "var(--aar-white)",
    }}>
      <form onSubmit={handleSubmit} className="card" style={{ width: 340 }}>
        <div className="brand" style={{ marginBottom: 24 }}>
          AAR <span>Audit</span>
        </div>
        <h3 style={{ marginBottom: 16 }}>Sign in</h3>

        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          style={fieldStyle}
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          style={fieldStyle}
        />

        {error && (
          <div style={{ color: "#c0392b", fontSize: 13, marginBottom: 12 }}>{error}</div>
        )}

        <button className="pill-button active" type="submit" disabled={submitting} style={{ width: "100%" }}>
          {submitting ? "Signing in…" : "Sign In"}
        </button>

        <div style={{ borderTop: "1px solid #e6e6e6", marginTop: 20, paddingTop: 16 }}>
          <button
            type="button"
            className="pill-button"
            style={{ width: "100%" }}
            onClick={() => {
              // DEV-ONLY BYPASS: fakes a logged-in frontend state so the
              // app shell/navigation can be exercised while the real
              // backend auth is still being wired up. Any actual API call
              // still goes to the real backend and gets a real 401/500
              // until that's genuinely working — this button doesn't
              // touch the backend's auth checks at all, it only skips
              // the frontend's login gate. Remove this button before
              // sharing this app with anyone else.
              localStorage.setItem("aar_token", "dev-bypass-token");
              localStorage.setItem("aar_role", "admin");
              onLoggedIn();
            }}
          >
            Continue without login (dev only)
          </button>
        </div>
      </form>
    </div>
  );
}

const fieldStyle = {
  display: "block",
  width: "100%",
  borderRadius: 999,
  border: "1px solid #e6e6e6",
  padding: "10px 16px",
  marginBottom: 12,
  fontSize: 14,
  boxSizing: "border-box",
};
