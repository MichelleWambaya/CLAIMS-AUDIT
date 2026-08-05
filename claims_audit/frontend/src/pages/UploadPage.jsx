import React, { useState } from "react";
import { api } from "../lib/api";
import { useSourceFiles } from "../lib/useSourceFiles";
import SourceFilesTable from "../components/SourceFilesTable";

export default function UploadPage({ sessionId }) {
  const { files, error, refresh } = useSourceFiles(sessionId);

  const [uploadFile, setUploadFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [uploadResult, setUploadResult] = useState(null);
  const [sheetOptions, setSheetOptions] = useState(null);
  const [selectedSheet, setSelectedSheet] = useState("");

  async function handleUpload(e) {
    e.preventDefault();
    if (!uploadFile) return;
    setUploading(true);
    setUploadError(null);
    setUploadResult(null);
    try {
      const result = await api.uploadFile(sessionId, uploadFile, selectedSheet || undefined);
      if (result.needs_sheet_selection) {
        setSheetOptions(result.sheets);
        return;
      }
      if (result.error) {
        setUploadError(result.schema_issues?.map((i) => i.detail).join("; ") || "Upload failed.");
        return;
      }
      setUploadResult(result);
      setSheetOptions(null);
      setSelectedSheet("");
      setUploadFile(null);
      refresh();
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div>
      <h1 style={{ marginBottom: 20 }}>Upload</h1>
      <p style={{ color: "#888", fontSize: 13, marginTop: -12, marginBottom: 20 }}>
        For testing, or smaller files where a manual upload is simpler than setting up a sync.
      </p>

      <div className="card" style={{ marginBottom: 24 }}>
        <h3 style={{ marginBottom: 12 }}>Upload a File</h3>
        <form onSubmit={handleUpload} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <input
            type="file"
            accept=".csv,.xlsx,.xlsm,.xls"
            onChange={(e) => { setUploadFile(e.target.files[0] || null); setSheetOptions(null); setUploadError(null); }}
          />
          {sheetOptions && (
            <select
              value={selectedSheet}
              onChange={(e) => setSelectedSheet(e.target.value)}
              style={{ borderRadius: 999, border: "1px solid #e6e6e6", padding: "8px 14px" }}
            >
              <option value="">Choose a sheet…</option>
              {sheetOptions.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          )}
          <button
            className="pill-button active"
            type="submit"
            disabled={uploading || !uploadFile || (sheetOptions && !selectedSheet)}
          >
            {uploading ? "Uploading…" : sheetOptions ? "Use This Sheet" : "Upload"}
          </button>
        </form>
        {uploadError && <div style={{ color: "#c0392b", fontSize: 13, marginTop: 10 }}>{uploadError}</div>}
        {uploadResult && (
          <div style={{ color: "#2e7d32", fontSize: 13, marginTop: 10 }}>
            Merged {uploadResult.rows_merged} rows as a {uploadResult.extract_type.replace("_", "-")} extract.
          </div>
        )}
        <div style={{ fontSize: 12, color: "#888", marginTop: 10 }}>
          CSV or Excel (.xlsx). If the workbook has multiple sheets, you'll be asked to pick one.
        </div>
      </div>

      {error && <div style={{ color: "#c0392b", fontSize: 13, marginBottom: 12 }}>{error}</div>}
      <SourceFilesTable files={files} />
    </div>
  );
}
