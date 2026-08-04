import React, { useEffect, useMemo, useState, useCallback } from "react";
import { api } from "./lib/api";
import TimePeriodPicker from "./components/TimePeriodPicker";
import KpiCards from "./components/KpiCards";
import CategoryChart from "./components/CategoryChart";
import TrendChart from "./components/TrendChart";
import ClaimsTable from "./components/ClaimsTable";
import FlagDetailPanel from "./components/FlagDetailPanel";
import ExportPanel from "./components/ExportPanel";

// In a real deployment this comes from session selection / routing.
const DEMO_SESSION_ID = window.__AAR_SESSION_ID__ || "demo-session";

export default function App() {
  const [timeRange, setTimeRange] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [selectedFlagType, setSelectedFlagType] = useState(null);
  const [selectedFlag, setSelectedFlag] = useState(null);

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [sortKey, setSortKey] = useState("id");
  const [sortDir, setSortDir] = useState("desc");

  const [flagsResponse, setFlagsResponse] = useState({ total: 0, flags: [] });
  const [reviewOverrides, setReviewOverrides] = useState({}); // flagId -> status, optimistic UI

  const loadFlags = useCallback(() => {
    api
      .listFlags(DEMO_SESSION_ID, {
        flagType: selectedFlagType || undefined,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      })
      .then(setFlagsResponse)
      .catch(() => setFlagsResponse({ total: 0, flags: [] }));
  }, [selectedFlagType, page, pageSize]);

  useEffect(() => { loadFlags(); }, [loadFlags]);

  // Cross-filtering (§6): selecting a category filters the table client-
  // side on top of the server-side flag-type filter, without a full
  // re-fetch — the category dimension isn't server-paginated in this
  // shell, since the category chart already holds the full aggregate.
  const visibleRows = useMemo(() => {
    let rows = flagsResponse.flags.map((f) => ({
      ...f,
      reviewStatus: reviewOverrides[f.id],
    }));
    if (selectedCategory) {
      rows = rows.filter((r) => r.detail?.category === selectedCategory);
    }
    rows.sort((a, b) => {
      const av = sortKey === "amount" ? (a.detail?.amount ?? 0) : a[sortKey] ?? a.detail?.[sortKey] ?? "";
      const bv = sortKey === "amount" ? (b.detail?.amount ?? 0) : b[sortKey] ?? b.detail?.[sortKey] ?? "";
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
    return rows;
  }, [flagsResponse, selectedCategory, reviewOverrides, sortKey, sortDir]);

  const categoryBreakdown = useMemo(() => {
    const counts = {};
    flagsResponse.flags.forEach((f) => {
      const cat = f.detail?.category || "Uncategorized";
      counts[cat] = (counts[cat] || 0) + 1;
    });
    return Object.entries(counts).map(([category, count]) => ({ category, count }));
  }, [flagsResponse]);

  const trendData = useMemo(() => {
    // Placeholder weekly bucketing until the backend exposes a dedicated
    // time-series endpoint — real implementation should aggregate
    // server-side rather than bucketing a single page of flags client-side.
    const buckets = {};
    flagsResponse.flags.forEach((f) => {
      const d = f.detail?.visit_date || f.detail?.claim_date;
      const key = d ? String(d).slice(0, 7) : "Unknown";
      buckets[key] = (buckets[key] || 0) + 1;
    });
    return Object.entries(buckets)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([period, flagCount]) => ({ period, flagCount }));
  }, [flagsResponse]);

  const kpis = useMemo(() => [
    { label: "Total Flags", value: flagsResponse.total.toLocaleString() },
    { label: "Duplicates", value: countByType(flagsResponse.flags, ["item_duplicate", "claim_duplicate"]), filterKey: "item_duplicate" },
    { label: "Non-Payable", value: countByType(flagsResponse.flags, ["non_payable"]), filterKey: "non_payable" },
    { label: "Pricing Anomalies", value: countByType(flagsResponse.flags, ["pricing_anomaly"]), filterKey: "pricing_anomaly" },
  ], [flagsResponse]);

  function handleReviewed(flagId, status) {
    setReviewOverrides((prev) => ({ ...prev, [flagId]: status }));
  }

  function handleSort(key) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">AAR <span>Audit</span></div>
        <nav style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 14 }}>
          <a href="#" style={{ color: "var(--aar-black)", textDecoration: "none", fontWeight: 600 }}>Dashboard</a>
          <a href="#" style={{ color: "#888", textDecoration: "none" }}>Source Files</a>
          <a href="#" style={{ color: "#888", textDecoration: "none" }}>Saved Views</a>
          <a href="#" style={{ color: "#888", textDecoration: "none" }}>Admin Config</a>
        </nav>
      </aside>

      <main className="main">
        <div className="topbar">
          <h1>Claims Forensic Audit</h1>
          <TimePeriodPicker onChange={setTimeRange} />
        </div>

        {selectedCategory && (
          <div style={{ marginBottom: 16 }}>
            <span className="filter-chip">
              Category: {selectedCategory}
              <button onClick={() => setSelectedCategory(null)}>×</button>
            </span>
          </div>
        )}

        <KpiCards
          kpis={kpis}
          activeKpiFilter={selectedFlagType}
          onSelect={(key) => { setSelectedFlagType(key); setPage(1); }}
        />

        <div className="grid-2">
          <CategoryChart
            data={categoryBreakdown}
            selectedCategory={selectedCategory}
            onSelectCategory={setSelectedCategory}
          />
          <TrendChart data={trendData} />
        </div>

        <div className="grid-2">
          <ClaimsTable
            rows={visibleRows}
            total={flagsResponse.total}
            page={page}
            pageSize={pageSize}
            onPageChange={setPage}
            onPageSizeChange={(n) => { setPageSize(n); setPage(1); }}
            sortKey={sortKey}
            sortDir={sortDir}
            onSort={handleSort}
            onRowClick={setSelectedFlag}
            selectedRowId={selectedFlag?.id}
          />
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <FlagDetailPanel sessionId={DEMO_SESSION_ID} flag={selectedFlag} onReviewed={handleReviewed} />
            <ExportPanel sessionId={DEMO_SESSION_ID} />
          </div>
        </div>
      </main>
    </div>
  );
}

function countByType(flags, types) {
  return flags.filter((f) => types.includes(f.flag_type)).length.toLocaleString();
}
