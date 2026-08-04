import React, { useState } from "react";
import { api } from "../lib/api";

/**
 * §8 audit trail: "an analyst can mark a flagged claim as confirmed,
 * false positive, or needs follow-up, with a note and timestamp."
 * Also exposes the §5.2 non-payable override path.
 */
export default function FlagDetailPanel({ sessionId, flag, onReviewed }) {
  const [note, setNote] = useState("");
  const [justification, setJustification] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (!flag) {
    return (
      <div className="card" style={{ color: "#888", fontSize: 13 }}>
        Select a row in the table to review it here.
      </div>
    );
  }

  async function submitReview(status) {
    setSubmitting(true);
    try {
      await api.reviewFlag(sessionId, flag.id, status, note);
      onReviewed(flag.id, status);
      setNote("");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitOverride() {
    if (!justification.trim()) return;
    setSubmitting(true);
    try {
      await api.overrideFlag(sessionId, flag.id, justification);
      onReviewed(flag.id, "overridden");
      setJustification("");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="card">
      <h3 style={{ marginBottom: 4 }}>Flag #{flag.id}</h3>
      <div style={{ fontSize: 12, color: "#666", marginBottom: 16 }}>{flag.flag_type}</div>

      <pre style={{
        background: "#f9f9f9", borderRadius: 8, padding: 12, fontSize: 12,
        overflowX: "auto", marginBottom: 16,
      }}>
        {JSON.stringify(flag.detail, null, 2)}
      </pre>

      <textarea
        placeholder="Add a note (optional)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        style={{ width: "100%", minHeight: 60, borderRadius: 8, border: "1px solid #e6e6e6", padding: 8, marginBottom: 10 }}
      />

      <div className="pill-group" style={{ marginBottom: 16 }}>
        <button className="pill-button active" disabled={submitting} onClick={() => submitReview("confirmed")}>
          Confirm
        </button>
        <button className="pill-button" disabled={submitting} onClick={() => submitReview("false_positive")}>
          False Positive
        </button>
        <button className="pill-button" disabled={submitting} onClick={() => submitReview("needs_follow_up")}>
          Needs Follow-up
        </button>
      </div>

      {flag.flag_type === "non_payable" && (
        <div style={{ borderTop: "1px solid #e6e6e6", paddingTop: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
            Legitimate exception (e.g. prescribed for a diagnosed deficiency)
          </div>
          <textarea
            placeholder="Justification for override"
            value={justification}
            onChange={(e) => setJustification(e.target.value)}
            style={{ width: "100%", minHeight: 50, borderRadius: 8, border: "1px solid #e6e6e6", padding: 8, marginBottom: 8 }}
          />
          <button className="pill-button" disabled={submitting} onClick={submitOverride}>
            Approve Override
          </button>
        </div>
      )}
    </div>
  );
}
