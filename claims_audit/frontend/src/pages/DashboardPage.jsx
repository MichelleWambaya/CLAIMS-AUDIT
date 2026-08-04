import React, { useEffect, useMemo, useState, useCallback } from "react";
import { api } from "../lib/api";
import TimePeriodPicker from "../components/TimePeriodPicker";
import KpiCards from "../components/KpiCards";
import CategoryChart from "../components/CategoryChart";
import TrendChart from "../components/TrendChart";
import ClaimsTable from "../components/ClaimsTable";
import FlagDetailPanel from "../components/FlagDetailPanel";
import ExportPanel from "../components/ExportPanel";

export default function DashboardPage({ sessionId }) {
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
      .listFlags(sessionId, {
        flagType: selectedFlagType || undefined,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      })
      .then(setFlagsResponse)
      .catch(() => setFlagsResponse({ total: 0, flags: [] }));
  }, [sessionId, selectedFlagType, page, pageSize]);

  useEffect(() => { loadFlags(); }, [loadFlags]);

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
    <div>
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
          <FlagDetailPanel sessionId={sessionId} flag={selectedFlag} onReviewed={handleReviewed} />
          <ExportPanel sessionId={sessionId} />
        </div>
      </div>
    </div>
  );
}

function countByType(flags, types) {
  return flags.filter((f) => types.includes(f.flag_type)).length.toLocaleString();
}
