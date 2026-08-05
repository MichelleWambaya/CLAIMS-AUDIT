import React, { useEffect, useState } from "react";
import { api } from "../lib/api";

/**
 * §8: "Configuration UI for every threshold in §5 ... with a change
 * history." The backend enforces admin-only writes (403 for analysts) —
 * this page doesn't duplicate that check, it just surfaces whatever the
 * server allows or rejects.
 */
export default function AdminConfigPage({ sessionId }) {
  const [config, setConfig] = useState(null);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState(null); // { type: 'success' | 'error', message }

  useEffect(() => {
    api.getRuleConfig(sessionId)
      .then((r) => setConfig(r.config))
      .catch((e) => setStatus({ type: "error", message: e.message }));
  }, [sessionId]);

  function updateField(path, value) {
    setConfig((prev) => ({ ...prev, [path]: value }));
  }

  async function handleSave() {
    setSaving(true);
    setStatus(null);
    try {
      await api.updateRuleConfig(sessionId, config);
      setStatus({ type: "success", message: "Thresholds updated." });
    } catch (err) {
      const isForbidden = err.message?.startsWith("403");
      setStatus({
        type: "error",
        message: isForbidden
          ? "Admin role required to change thresholds."
          : err.message,
      });
    } finally {
      setSaving(false);
    }
  }

  if (!config) {
    return <div style={{ padding: 20, color: "#888" }}>Loading configuration…</div>;
  }

  return (
    <div>
      <h1 style={{ marginBottom: 20 }}>Admin Configuration</h1>

      <div className="card" style={{ marginBottom: 20, maxWidth: 560 }}>
        <h3 style={{ marginBottom: 12 }}>Duplicate Detection (§5.1)</h3>
        <FieldRow label="Day window">
          <input
            type="number"
            value={config.duplicate_day_window}
            onChange={(e) => updateField("duplicate_day_window", Number(e.target.value))}
            style={inputStyle}
          />
        </FieldRow>
        <FieldRow label="Similarity threshold (0–1)">
          <input
            type="number"
            step="0.01"
            min="0"
            max="1"
            value={config.duplicate_similarity_threshold}
            onChange={(e) => updateField("duplicate_similarity_threshold", Number(e.target.value))}
            style={inputStyle}
          />
        </FieldRow>
        <FieldRow label="Eligible ITEM_STATUS values (comma-separated)">
          <input
            type="text"
            value={(config.duplicate_eligible_item_statuses || []).join(", ")}
            onChange={(e) =>
              updateField("duplicate_eligible_item_statuses", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))
            }
            style={inputStyle}
          />
        </FieldRow>
      </div>

      <div className="card" style={{ marginBottom: 20, maxWidth: 560 }}>
        <h3 style={{ marginBottom: 12 }}>Pricing Anomalies (§5.3)</h3>
        <FieldRow label="Default IQR multiplier">
          <input
            type="number"
            step="0.1"
            value={config.iqr_multiplier_default}
            onChange={(e) => updateField("iqr_multiplier_default", Number(e.target.value))}
            style={inputStyle}
          />
        </FieldRow>
        <div style={{ fontSize: 12, color: "#888" }}>
          Per-category overrides (<code>iqr_multiplier_by_category</code>) aren't
          editable from this simple form yet — that needs a per-category row
          editor, which is a reasonable next addition once this basic form is
          proven out.
        </div>
      </div>

      <div className="card" style={{ marginBottom: 20, maxWidth: 560 }}>
        <h3 style={{ marginBottom: 12 }}>Non-Payable Keywords (§5.2)</h3>
        <div style={{ fontSize: 13, color: "#666" }}>
          {Object.keys(config.non_payable_keywords || {}).length} categories,{" "}
          {Object.values(config.non_payable_keywords || {}).reduce((sum, arr) => sum + arr.length, 0)} keywords total.
        </div>
        <div style={{ fontSize: 12, color: "#888", marginTop: 6 }}>
          Editing individual keywords needs a dedicated list editor — out of
          scope for this first pass, but the data's already structured for it
          (one array per category in <code>non_payable_keywords</code>).
        </div>
      </div>

      <button className="pill-button active" onClick={handleSave} disabled={saving}>
        {saving ? "Saving…" : "Save Changes"}
      </button>

      {status && (
        <div style={{ marginTop: 12, fontSize: 13, color: status.type === "error" ? "#c0392b" : "#2e7d32" }}>
          {status.message}
        </div>
      )}
    </div>
  );
}

function FieldRow({ label, children }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
      <label style={{ fontSize: 13 }}>{label}</label>
      {children}
    </div>
  );
}

const inputStyle = {
  borderRadius: 999,
  border: "1px solid #e6e6e6",
  padding: "6px 12px",
  width: 160,
  textAlign: "right",
};
