import React, { useState } from "react";
import { api } from "../lib/api";

export default function LoginPage({ onLoggedIn }) {
  const [mode, setMode] = useState("login"); // "login" | "signup"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const result =
        mode === "login"
          ? await api.login(email, password)
          : await api.signup(email, password, displayName);

      if (!result.access_token) {
        throw new Error(result.detail || `${mode === "login" ? "Login" : "Signup"} failed`);
      }
      localStorage.setItem("aar_token", result.access_token);
      localStorage.setItem("aar_role", result.role);
      onLoggedIn();
    } catch (err) {
      setError(
        mode === "login"
          ? "Incorrect email or password."
          : "Couldn't create that account — the email may already be in use, or the password may be too short (minimum 8 characters)."
      );
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
        <h3 style={{ marginBottom: 16 }}>{mode === "login" ? "Sign in" : "Create account"}</h3>

        {mode === "signup" && (
          <input
            type="text"
            placeholder="Your name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            required
            style={fieldStyle}
          />
        )}
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
          minLength={mode === "signup" ? 8 : undefined}
          style={fieldStyle}
        />
        {mode === "signup" && (
          <div style={{ fontSize: 12, color: "#777", marginTop: -6, marginBottom: 12 }}>
            Minimum 8 characters. The very first account created on this deployment
            automatically becomes admin.
          </div>
        )}

        {error && (
          <div style={{ color: "#c0392b", fontSize: 13, marginBottom: 12 }}>{error}</div>
        )}

        <button className="pill-button active" type="submit" disabled={submitting} style={{ width: "100%" }}>
          {submitting
            ? (mode === "login" ? "Signing in…" : "Creating account…")
            : (mode === "login" ? "Sign In" : "Create Account")}
        </button>

        <div style={{ borderTop: "1px solid #e6e6e6", marginTop: 20, paddingTop: 16, textAlign: "center" }}>
          {mode === "login" ? (
            <button
              type="button"
              className="pill-button"
              style={{ width: "100%" }}
              onClick={() => { setMode("signup"); setError(null); }}
            >
              Need an account? Sign up
            </button>
          ) : (
            <button
              type="button"
              className="pill-button"
              style={{ width: "100%" }}
              onClick={() => { setMode("login"); setError(null); }}
            >
              Already have an account? Sign in
            </button>
          )}
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
