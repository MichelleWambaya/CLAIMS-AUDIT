import React, { useState, useEffect } from "react";
import DashboardPage from "./pages/DashboardPage";
import SyncPage from "./pages/SyncPage";
import UploadPage from "./pages/UploadPage";
import SavedViewsPage from "./pages/SavedViewsPage";
import AdminConfigPage from "./pages/AdminConfigPage";
import LoginPage from "./pages/LoginPage";
import { api } from "./lib/api";

const NAV_ITEMS = [
  { key: "dashboard", label: "Dashboard" },
  { key: "sync", label: "Sync" },
  { key: "upload", label: "Upload" },
  { key: "savedViews", label: "Saved Views" },
  { key: "adminConfig", label: "Admin Config" },
];

export default function App() {
  const [activePage, setActivePage] = useState("dashboard");
  const [isLoggedIn, setIsLoggedIn] = useState(!!localStorage.getItem("aar_token"));
  const [sessionId, setSessionId] = useState(localStorage.getItem("aar_session_id"));
  const [sessionError, setSessionError] = useState(null);

  // A real audit session is required before any /sessions/{id}/... call
  // can succeed (the DB column is a UUID, not an arbitrary string) — so
  // create one automatically on first login rather than relying on a
  // placeholder ID that was never wired up to anything real.
  useEffect(() => {
    if (isLoggedIn && !sessionId) {
      api
        .createSession("Default Session")
        .then((result) => {
          localStorage.setItem("aar_session_id", result.id);
          setSessionId(result.id);
        })
        .catch((err) => setSessionError(err.message));
    }
  }, [isLoggedIn, sessionId]);

  function handleLogout() {
    localStorage.removeItem("aar_token");
    localStorage.removeItem("aar_role");
    localStorage.removeItem("aar_session_id");
    setIsLoggedIn(false);
    setSessionId(null);
  }

  if (!isLoggedIn) {
    return <LoginPage onLoggedIn={() => setIsLoggedIn(true)} />;
  }

  if (sessionError) {
    return (
      <div style={{ padding: 40, color: "#c0392b" }}>
        Couldn't create or load an audit session: {sessionError}
      </div>
    );
  }

  if (!sessionId) {
    return <div style={{ padding: 40, color: "#888" }}>Setting up your session…</div>;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">AAR <span>Audit</span></div>
        <nav style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 14 }}>
          {NAV_ITEMS.map((item) => (
            <a
              key={item.key}
              href="#"
              onClick={(e) => { e.preventDefault(); setActivePage(item.key); }}
              style={{
                color: activePage === item.key ? "var(--aar-black)" : "#888",
                textDecoration: "none",
                fontWeight: activePage === item.key ? 600 : 400,
              }}
            >
              {item.label}
            </a>
          ))}
          <a
            href="#"
            onClick={(e) => { e.preventDefault(); handleLogout(); }}
            style={{ color: "#888", textDecoration: "none", marginTop: 20 }}
          >
            Log out
          </a>
        </nav>
      </aside>

      <main className="main">
        {activePage === "dashboard" && <DashboardPage sessionId={sessionId} />}
        {activePage === "sync" && <SyncPage sessionId={sessionId} />}
        {activePage === "upload" && <UploadPage sessionId={sessionId} />}
        {activePage === "savedViews" && <SavedViewsPage sessionId={sessionId} />}
        {activePage === "adminConfig" && <AdminConfigPage sessionId={sessionId} />}
      </main>
    </div>
  );
}
