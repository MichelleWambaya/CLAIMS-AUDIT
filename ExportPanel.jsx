import React, { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";

/**
 * §7: exports run as background jobs with a ready-state notification, and
 * §"stored" requirement from the updated brief: past reports stay
 * browsable here, not just a single download link that disappears.
 */
export default function ExportPanel({ sessionId }) {
  const [reports, setReports] = useState([]);
  const [requesting, setRequesting] = useState(null);

  const refresh = useCallback(() => {
    api.listReports(sessionId).then(setReports).catch(() => {});
  }, [sessionId]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 4000); // poll while any report is generating
    return () => clearInterval(interval);
  }, [refresh]);

  async function requestReport(type) {
    setRequesting(type);
    try {
      await api.requestReport(sessionId, type);
      refresh();
    } finally {
      setRequesting(null);
    }
  }

  return (
    <div className="card">
      <h3 style={{ marginBottom: 12 }}>Export & Present</h3>
      <div className="pill-group" style={{ marginBottom: 16 }}>
        <button className="pill-button" disabled={requesting} onClick={() => requestReport("pptx")}>
          {requesting === "pptx" ? "Queuing…" : "Generate PPTX"}
        </button>
        <button className="pill-button" disabled={requesting} onClick={() => requestReport("pdf")}>
          {requesting === "pdf" ? "Queuing…" : "Generate PDF"}
        </button>
        <button className="pill-button" disabled={requesting} onClick={() => requestReport("xlsx")}>
          {requesting === "xlsx" ? "Queuing…" : "Generate Excel"}
        </button>
      </div>

      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>Past Reports</div>
      {reports.length === 0 && <div style={{ fontSize: 13, color: "#888" }}>No reports generated yet.</div>}
      <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {reports.map((r) => (
          <li key={r.id} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid #f2f2f2", fontSize: 13 }}>
            <span>{r.report_type.toUpperCase()} · {new Date(r.created_at).toLocaleString()}</span>
            <span>
              {r.status === "ready" ? (
                <a href={`/api/downloads/${encodeURIComponent(r.download_key)}`} style={{ color: "var(--aar-orange)", fontWeight: 600 }}>
                  Download
                </a>
              ) : r.status === "error" ? (
                <span style={{ color: "#c0392b" }}>Failed</span>
              ) : (
                <span style={{ color: "#888" }}>{r.status}…</span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
