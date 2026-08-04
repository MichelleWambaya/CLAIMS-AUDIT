import React from "react";

/**
 * Each KPI is clickable and acts as a filter trigger (§6 cross-filtering:
 * "clicking a bar, slice, or table row filters every other visual").
 * `activeKpiFilter` highlights the currently-applied one.
 */
export default function KpiCards({ kpis, activeKpiFilter, onSelect }) {
  return (
    <div className="kpi-grid">
      {kpis.map((kpi) => {
        const isActive = activeKpiFilter === kpi.filterKey;
        return (
          <div
            key={kpi.label}
            className={`kpi-card ${kpi.filterKey ? "clickable" : ""}`}
            style={isActive ? { boxShadow: "0 0 0 2px var(--aar-orange)" } : undefined}
            onClick={() => kpi.filterKey && onSelect(isActive ? null : kpi.filterKey)}
            title={kpi.filterKey ? "Click to filter the dashboard to this flag type" : undefined}
          >
            <div className="value">{kpi.value}</div>
            <div className="label">{kpi.label}</div>
          </div>
        );
      })}
    </div>
  );
}
