import React, { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";

/**
 * §6/§8: an analyst can save a filtered dashboard configuration (time
 * range, dimension breakdown) and return to it later or hand it to a
 * colleague. This page lists existing saved views and lets you create
 * one from a manually-entered config — in the full dashboard, "Save
 * Current View" from the Dashboard page would prefill this from live
 * filter state instead of typing JSON by hand.
 */
export default function SavedViewsPage({ sessionId }) {
  const [views, setViews] = useState([]);
  const [name, setName] = useState("");
  const [timePreset, setTimePreset] = useState("this_quarter");
  const [category, setCategory] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const refresh = useCallback(() => {
    api.listSavedViews(sessionId).then(setViews).catch((e) => setError(e.message));
  }, [sessionId]);

  useEffect(() => { refresh(); }, [refresh]);

  async function handleSave(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await api.saveView(sessionId, name.trim(), {
        time_range_preset: timePreset,
        category_filter: category.trim() || null,
      });
      setName("");
      setCategory("");
      refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h1 style={{ marginBottom: 20 }}>Saved Views</h1>

      <div className="card" style={{ marginBottom: 24 }}>
        <h3 style={{ marginBottom: 12 }}>Save a New View</h3>
        <form onSubmit={handleSave} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <input
            placeholder="View name (e.g. Nairobi Q3 Pricing Review)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ borderRadius: 999, border: "1px solid #e6e6e6", padding: "8px 14px", flex: "1 1 260px" }}
          />
          <select
            value={timePreset}
            onChange={(e) => setTimePreset(e.target.value)}
            style={{ borderRadius: 999, border: "1px solid #e6e6e6", padding: "8px 14px" }}
          >
            <option value="this_month">This Month</option>
            <option value="last_month">Last Month</option>
            <option value="this_quarter">This Quarter</option>
            <option value="last_quarter">Last Quarter</option>
            <option value="ytd">YTD</option>
            <option value="all_time">All Time</option>
          </select>
          <input
            placeholder="Category filter (optional)"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            style={{ borderRadius: 999, border: "1px solid #e6e6e6", padding: "8px 14px", flex: "1 1 180px" }}
          />
          <button className="pill-button active" type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save View"}
          </button>
        </form>
        {error && <div style={{ color: "#c0392b", fontSize: 13, marginTop: 10 }}>{error}</div>}
      </div>

      <div className="card">
        <h3 style={{ marginBottom: 12 }}>Saved Views ({views.length})</h3>
        {views.length === 0 ? (
          <div style={{ color: "#888", fontSize: 13 }}>No saved views yet.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Time Range</th>
                <th>Category</th>
              </tr>
            </thead>
            <tbody>
              {views.map((v) => (
                <tr key={v.id}>
                  <td>{v.name}</td>
                  <td>{v.view_config?.time_range_preset ?? "—"}</td>
                  <td>{v.view_config?.category_filter ?? "All"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
