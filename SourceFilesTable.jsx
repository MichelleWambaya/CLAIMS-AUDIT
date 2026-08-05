import React from "react";

const STATUS_COLORS = {
  pending: "#888",
  parsing: "#f3781f",
  parsed: "#f3781f",
  merged: "#2e7d32",
  error: "#c0392b",
};

export default function SourceFilesTable({ files }) {
  return (
    <div className="card">
      <h3 style={{ marginBottom: 12 }}>Batches in this Session ({files.length})</h3>
      <table>
        <thead>
          <tr>
            <th>File Name</th>
            <th>Source</th>
            <th>Extract Type</th>
            <th>Status</th>
            <th>Rows</th>
            <th>Schema Issues</th>
          </tr>
        </thead>
        <tbody>
          {files.map((f) => (
            <tr key={f.id}>
              <td>{f.file_name}</td>
              <td>{f.source_type ?? "—"}</td>
              <td>{f.extract_type ?? "—"}</td>
              <td style={{ color: STATUS_COLORS[f.status] || "#333", fontWeight: 600 }}>
                {f.status}
              </td>
              <td>{f.row_count != null ? f.row_count.toLocaleString() : "—"}</td>
              <td style={{ fontSize: 12, color: "#c0392b" }}>
                {f.schema_issues && f.schema_issues.length > 0
                  ? f.schema_issues.map((i) => i.detail).join("; ")
                  : "—"}
              </td>
            </tr>
          ))}
          {files.length === 0 && (
            <tr>
              <td colSpan={6} style={{ textAlign: "center", padding: 24, color: "#888" }}>
                No files yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
