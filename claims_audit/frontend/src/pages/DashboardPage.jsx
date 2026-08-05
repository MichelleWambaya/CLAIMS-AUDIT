import React, { useEffect, useMemo, useState, useCallback } from "react";
import { api } from "../lib/api";
import TimePeriodPicker from "../components/TimePeriodPicker";
import KpiCards from "../components/KpiCards";
import CategoryChart from "../components/CategoryChart";
import TrendChart from "../components/TrendChart";
import ClaimsTable from "../components/ClaimsTable";
import FlagDetailPanel from "../components/FlagDetailPanel";
import ExportPanel from "../components/ExportPanel";

// The only 6 flag types the rule engine actually produces today
// (api/routers/flags.py:recompute_flags) — kept in one place so the
// dropdown can never drift out of sync with what the backend computes.
const CATEGORIES = [
  { key: null, label: "All categories (consolidated)" },
  { key: "item_duplicate", label: "Duplicate items" },
  { key: "claim_duplicate", label: "Duplicate claims" },
  { key: "non_payable", label: "Non-payable categories" },
  { key: "pricing_anomaly", label: "Pricing anomalies" },
  { key: "invalid_member_policy", label: "Invalid member/policy" },
  { key: "diagnosis_gap", label: "Diagnosis gaps" },
];

function labelFor(key) {
  return CATEGORIES.find((c) => c.key === key)?.label ?? key;
}

export default function DashboardPage({ sessionId }) {
  const [timeRange, setTimeRange] = useState(null);
  const [selectedFlagType, setSelectedFlagType] = useState(null); // null = consolidated
  const [selectedFlag, setSelectedFlag] = useState(null);

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [sortKey, setSortKey] = useState("id");
  const [sortDir, setSortDir] = useState("desc");

  const [flagsResponse, setFlagsResponse] = useState({ total: 0, flags: [] });
  const [allFlagsForKpis, setAllFlagsForKpis] = useState([]); // unfiltered, for the KPI row's counts
  const [reviewOverrides, setReviewOverrides] = useState({});

  // Table data: respects the dropdown filter + pagination.
  const loadFlags = useCallback(() => { api
      .listFlags(sessionId, {
        flagType: selectedFlagType || undefined,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      })
      .then(setFlagsResponse)
      .catch(() => setFlagsResponse({ total: 0, flags: [] }));
  }, [sessionId, selectedFlagType, page, pageSize]);

  useEffect(() => { loadFlags(); }, [loadFlags]);

  // KPI row and charts need counts across ALL categories regardless of the
  // dropdown, so they're loaded separately from the filtered table data.
  // 2000 is a pragmatic cap for in-browser aggregation — a session with
  // more flags than that would want server-side aggregation instead (see
  // README "Known remaining work").
  useEffect(() => {
    api
      .listFlags(sessionId, { limit: 2000, offset: 0 })
      .then((res) => setAllFlagsForKpis(res.flags))
      .catch(() => setAllFlagsForKpis([]));
  }, [sessionId]);

  const visibleRows = useMemo(() => {
    const rows = flagsResponse.flags.map((f) => ({
      ...f,
      reviewStatus: reviewOverrides[f.id],
    }));
    rows.sort((a, b) => {
      const av = sortKey === "amount" ? (a.detail?.amount ?? 0) : a[sortKey] ?? a.detail?.[sortKey] ?? "";
      const bv = sortKey === "amount" ? (b.detail?.amount ?? 0) : b[sortKey] ?? b.detail?.[sortKey] ?? "";
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
    return rows;
  }, [flagsResponse, reviewOverrides, sortKey, sortDir]);

  // KPI cards: one per real flag type, always visible regardless of the
  // dropdown, so switching categories never hides the overall picture.
  const kpis = useMemo(() => {
    const countOf = (type) => allFlagsForKpis.filter((f) => f.flag_type === type).length;
    return [
      { label: "Total Flags", value: allFlagsForKpis.length.toLocaleString() },
      { label: "Duplicate Items", value: countOf("item_duplicate").toLocaleString(), filterKey: "item_duplicate" },
      { label: "Duplicate Claims", value: countOf("claim_duplicate").toLocaleString(), filterKey: "claim_duplicate" },
      { label: "Non-Payable", value: countOf("non_payable").toLocaleString(), filterKey: "non_payable" },
      { label: "Pricing Anomalies", value: countOf("pricing_anomaly").toLocaleString(), filterKey: "pricing_anomaly" },
      { label: "Invalid Member/Policy", value: countOf("invalid_member_policy").toLocaleString(), filterKey: "invalid_member_policy" },
      { label: "Diagnosis Gaps", value: countOf("diagnosis_gap").toLocaleString(), filterKey: "diagnosis_gap" },
    ];
  }, [allFlagsForKpis]);

  // Consolidated view: one bar per flag type, across the whole session.
  const consolidatedBreakdown = useMemo(() => {
    const counts = {};
    allFlagsForKpis.forEach((f) => {
      counts[f.flag_type] = (counts[f.flag_type] || 0) + 1;
    });
    return Object.entries(counts).map(([flagType, count]) => ({
      category: labelFor(flagType),
      count,
    }));
  }, [allFlagsForKpis]);

  // Single-category view: break the selected type down by whatever
  // secondary dimension is most meaningful for that specific rule —
  // falls back to a generic "matched value" grouping if the detail
  // shape doesn't have a more specific field.
  const singleCategoryBreakdown = useMemo(() => {
    if (!selectedFlagType) return [];
    const counts = {};
    allFlagsForKpis
      .filter((f) => f.flag_type === selectedFlagType)
      .forEach((f) => {
        const d = f.detail || {};
        let key;
        if (selectedFlagType === "non_payable") key = d.category || d.matched_field || "Uncategorized";
        else if (selectedFlagType === "pricing_anomaly") key = d.category || "Uncategorized";
        else if (selectedFlagType === "invalid_member_policy") key = d.reason || "Uncategorized";
        else if (selectedFlagType === "diagnosis_gap") key = d.reason || "Missing diagnosis data";
        else key = d.category || d.provider || "Uncategorized";
        counts[key] = (counts[key] || 0) + 1;
      });
    return Object.entries(counts).map(([category, count]) => ({ category, count }));
  }, [allFlagsForKpis, selectedFlagType]);

  const trendData = useMemo(() => {
    const source = selectedFlagType
      ? allFlagsForKpis.filter((f) => f.flag_type === selectedFlagType)
      : allFlagsForKpis;
    const buckets = {};
    source.forEach((f) => {
      const d = f.detail?.visit_date || f.detail?.claim_date;
      const key = d ? String(d).slice(0, 7) : "Unknown";
      buckets[key] = (buckets[key] || 0) + 1;
    });
    return Object.entries(buckets)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([period, flagCount]) => ({ period, flagCount }));
  }, [allFlagsForKpis, selectedFlagType]);

  // Rough financial-impact estimate: sums whatever `amount` figure is
  // present on each flag's detail blob. Not every flag type carries a
  // dollar amount (e.g. diagnosis gaps don't), so this is a lower bound,
  // not a complete loss total — worth saying plainly rather than
  // implying more precision than the underlying data supports.
  const totalFlaggedAmount = useMemo(() => {
    const source = selectedFlagType
      ? allFlagsForKpis.filter((f) => f.flag_type === selectedFlagType)
      : allFlagsForKpis;
    return source.reduce((sum, f) => { const amt = Number(f.detail?.amount); return sum + (Number.isFinite(amt) ? amt : 0); }, 0);
  }, [allFlagsForKpis, selectedFlagType]);

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
      <div className="topbar" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        <h1>Claims Forensic Audit</h1>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <select
            value={selectedFlagType || ""}
            onChange={(e) => { setSelectedFlagType(e.target.value || null); setPage(1); }}
            style={{
              borderRadius: 999, border: "1px solid #e6e6e6", padding: "8px 16px",
              fontSize: 14, background: "white", minWidth: 240,
            }}
          >
            {CATEGORIES.map((c) => (
              <option key={c.key ?? "all"} value={c.key ?? ""}>{c.label}</option>
            ))}
          </select>
          <TimePeriodPicker onChange={setTimeRange} />
        </div>
      </div>

      <KpiCards
        kpis={kpis}
        activeKpiFilter={selectedFlagType}
        onSelect={(key) => { setSelectedFlagType(key); setPage(1); }}
      />

      <div className="grid-2">
        <CategoryChart
          data={selectedFlagType ? singleCategoryBreakdown : consolidatedBreakdown}
          selectedCategory={null}
          onSelectCategory={() => {}}
        />
        <TrendChart data={trendData} />
      </div>

      <div className="card" style={{ margin: "16px 0", padding: "16px 24px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div style={{ fontSize: 13, color: "#777" }}>
            {selectedFlagType ? `Flagged amount — ${labelFor(selectedFlagType)}` : "Total flagged amount — all categories"}
          </div>
          <div style={{ fontSize: 24, fontWeight: 600 }}>
            {totalFlaggedAmount.toLocaleString(undefined, { style: "currency", currency: "USD" })}
          </div>
          <div style={{ fontSize: 12, color: "#999" }}>
            Lower-bound estimate — not every flag type carries a claim amount (e.g. diagnosis gaps).
          </div>
        </div>
        {selectedFlagType && (
          <button className="pill-button" onClick={() => { setSelectedFlagType(null); setPage(1); }}>
            Clear filter
          </button>
        )}
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
