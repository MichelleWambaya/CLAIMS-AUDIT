import React, { useState } from "react";

const PRESETS = [
  { key: "this_month", label: "This Month" },
  { key: "last_month", label: "Last Month" },
  { key: "this_quarter", label: "This Quarter" },
  { key: "last_quarter", label: "Last Quarter" },
  { key: "ytd", label: "YTD" },
  { key: "all_time", label: "All Time" },
];

function presetToRange(key) {
  const now = new Date();
  const startOfMonth = (y, m) => new Date(y, m, 1);
  const endOfMonth = (y, m) => new Date(y, m + 1, 0);

  switch (key) {
    case "this_month":
      return [startOfMonth(now.getFullYear(), now.getMonth()), now];
    case "last_month":
      return [
        startOfMonth(now.getFullYear(), now.getMonth() - 1),
        endOfMonth(now.getFullYear(), now.getMonth() - 1),
      ];
    case "this_quarter": {
      const q = Math.floor(now.getMonth() / 3);
      return [startOfMonth(now.getFullYear(), q * 3), now];
    }
    case "last_quarter": {
      const q = Math.floor(now.getMonth() / 3) - 1;
      const year = q < 0 ? now.getFullYear() - 1 : now.getFullYear();
      const qNorm = q < 0 ? 3 : q;
      return [startOfMonth(year, qNorm * 3), endOfMonth(year, qNorm * 3 + 2)];
    }
    case "ytd":
      return [startOfMonth(now.getFullYear(), 0), now];
    case "all_time":
    default:
      return [null, null];
  }
}

/**
 * Concise time-period control per the updated spec: a few presets + one
 * custom range, rather than a full BI-style axis configuration. Calls
 * onChange({ preset, dateFrom, dateTo }) whenever the selection changes.
 */
export default function TimePeriodPicker({ onChange }) {
  const [activePreset, setActivePreset] = useState("this_quarter");
  const [showCustom, setShowCustom] = useState(false);
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");

  function selectPreset(key) {
    setActivePreset(key);
    setShowCustom(false);
    const [from, to] = presetToRange(key);
    onChange({
      preset: key,
      dateFrom: from ? from.toISOString().slice(0, 10) : null,
      dateTo: to ? to.toISOString().slice(0, 10) : null,
    });
  }

  function applyCustom() {
    setActivePreset("custom");
    onChange({ preset: "custom", dateFrom: customFrom || null, dateTo: customTo || null });
  }

  return (
    <div>
      <div className="pill-group">
        {PRESETS.map((p) => (
          <button
            key={p.key}
            className={`pill-button ${activePreset === p.key ? "active" : ""}`}
            onClick={() => selectPreset(p.key)}
          >
            {p.label}
          </button>
        ))}
        <button
          className={`pill-button ${activePreset === "custom" ? "active" : ""}`}
          onClick={() => setShowCustom((s) => !s)}
        >
          Custom
        </button>
      </div>

      {showCustom && (
        <div style={{ marginTop: 10, display: "flex", gap: 8, alignItems: "center" }}>
          <input
            type="date"
            value={customFrom}
            onChange={(e) => setCustomFrom(e.target.value)}
            style={{ borderRadius: 999, border: "1px solid #e6e6e6", padding: "6px 12px" }}
          />
          <span>to</span>
          <input
            type="date"
            value={customTo}
            onChange={(e) => setCustomTo(e.target.value)}
            style={{ borderRadius: 999, border: "1px solid #e6e6e6", padding: "6px 12px" }}
          />
          <button className="pill-button active" onClick={applyCustom}>
            Apply
          </button>
        </div>
      )}
    </div>
  );
}
