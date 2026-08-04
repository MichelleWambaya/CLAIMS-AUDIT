import React, { useMemo, useState } from "react";

const PAGE_SIZE_OPTIONS = [25, 50, 100, 250];

/**
 * §6: "no artificial row cap ... replaced with real pagination or
 * virtualized scrolling so nothing is silently hidden from view."
 * Server-side pagination via api.listFlags({limit, offset}) means this
 * component never holds more than one page in memory regardless of how
 * many total flags exist.
 */
export default function ClaimsTable({
  rows, total, page, pageSize, onPageChange, onPageSizeChange,
  sortKey, sortDir, onSort, onRowClick, selectedRowId,
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const columns = [
    { key: "flag_type", label: "Flag Type" },
    { key: "member_id", label: "Member" },
    { key: "category", label: "Category" },
    { key: "amount", label: "Amount" },
    { key: "reason", label: "Reason" },
    { key: "review_status", label: "Status" },
  ];

  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h3>Flagged Claims ({total.toLocaleString()})</h3>
      </div>

      <table>
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} onClick={() => onSort(col.key)}>
                {col.label}
                {sortKey === col.key && (sortDir === "asc" ? " ▲" : " ▼")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              className={selectedRowId === row.id ? "selected-row" : ""}
              onClick={() => onRowClick(row)}
              style={{ cursor: "pointer" }}
            >
              <td>{row.flag_type}</td>
              <td>{row.detail?.member_id ?? "—"}</td>
              <td>{row.detail?.category ?? "—"}</td>
              <td>{row.detail?.amount != null ? Number(row.detail.amount).toLocaleString() : "—"}</td>
              <td>{row.detail?.reason ?? row.detail?.matched_keyword ?? row.flag_type}</td>
              <td>{row.reviewStatus ?? "unreviewed"}</td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={columns.length} style={{ textAlign: "center", padding: 24, color: "#888" }}>
                No flags match the current filters.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <div className="pagination">
        <select
          value={pageSize}
          onChange={(e) => onPageSizeChange(Number(e.target.value))}
          style={{ borderRadius: 999, border: "1px solid #e6e6e6", padding: "4px 10px" }}
        >
          {PAGE_SIZE_OPTIONS.map((n) => (
            <option key={n} value={n}>{n} / page</option>
          ))}
        </select>
        <button className="pill-button" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
          Prev
        </button>
        <span>Page {page} of {totalPages}</span>
        <button className="pill-button" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
          Next
        </button>
      </div>
    </div>
  );
}
