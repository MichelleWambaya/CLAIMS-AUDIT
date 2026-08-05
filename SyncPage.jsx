import React, { useState } from "react";
import { api } from "../lib/api";
import { useSourceFiles } from "../lib/useSourceFiles";
import SourceFilesTable from "../components/SourceFilesTable";

export default function SyncPage({ sessionId }) {
  const { files, error, refresh } = useSourceFiles(sessionId);

  const [linkUrl, setLinkUrl] = useState("");
  const [linkSyncing, setLinkSyncing] = useState(false);
  const [linkError, setLinkError] = useState(null);
  const [linkResult, setLinkResult] = useState(null);
  const [linkSheetOptions, setLinkSheetOptions] = useState(null);
  const [linkSelectedSheet, setLinkSelectedSheet] = useState("");

  const [driveId, setDriveId] = useState("");
  const [folderPath, setFolderPath] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState(null);

  async function handleLinkSync(e) {
    e.preventDefault();
    if (!linkUrl.trim()) return;
    setLinkSyncing(true);
    setLinkError(null);
    setLinkResult(null);
    try {
      const result = await api.linkSync(sessionId, linkUrl.trim(), linkSelectedSheet || undefined);
      if (result.needs_sheet_selection) {
        setLinkSheetOptions(result.sheets);
        return;
      }
      if (result.error) {
        setLinkError(result.schema_issues?.map((i) => i.detail).join("; ") || "Sync failed.");
        return;
      }
      setLinkResult(result);
      setLinkSheetOptions(null);
      setLinkSelectedSheet("");
      refresh();
    } catch (err) {
      setLinkError(err.message);
    } finally {
      setLinkSyncing(false);
    }
  }

  async function handleOneDriveSync(e) {
    e.preventDefault();
    if (!driveId.trim() || !folderPath.trim()) return;
    setSyncing(true);
    setSyncError(null);
    try {
      await api.triggerSync(sessionId, driveId.trim(), folderPath.trim());
      refresh();
    } catch (err) {
      setSyncError(err.message);
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div>
      <h1 style={{ marginBottom: 20 }}>Sync</h1>

      <div className="card" style={{ marginBottom: 24 }}>
        <h3 style={{ marginBottom: 12 }}>Sync from a Shared Link</h3>
        <form onSubmit={handleLinkSync} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <input
            placeholder="Paste a OneDrive/SharePoint share link"
            value={linkUrl}
            onChange={(e) => setLinkUrl(e.target.value)}
            style={{ borderRadius: 999, border: "1px solid #e6e6e6", padding: "8px 14px", flex: "1 1 320px" }}
          />
          {linkSheetOptions && (
            <select
              value={linkSelectedSheet}
              onChange={(e) => setLinkSelectedSheet(e.target.value)}
              style={{ borderRadius: 999, border: "1px solid #e6e6e6", padding: "8px 14px" }}
            >
              <option value="">Choose a sheet…</option>
              {linkSheetOptions.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          )}
          <button
            className="pill-button active"
            type="submit"
            disabled={linkSyncing || !linkUrl.trim() || (linkSheetOptions && !linkSelectedSheet)}
          >
            {linkSyncing ? "Syncing…" : linkSheetOptions ? "Use This Sheet" : "Sync Now"}
          </button>
        </form>
        {linkError && <div style={{ color: "#c0392b", fontSize: 13, marginTop: 10 }}>{linkError}</div>}
        {linkResult && (
          <div style={{ color: "#2e7d32", fontSize: 13, marginTop: 10 }}>
            Merged {linkResult.rows_merged} rows as a {linkResult.extract_type.replace("_", "-")} extract.
          </div>
        )}
        <div style={{ fontSize: 12, color: "#888", marginTop: 10 }}>
          The file's sharing setting must be "Anyone with the link can view" — Sync Now
          re-fetches the current version on demand (not on an automatic schedule).
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h3 style={{ marginBottom: 12 }}>Sync from OneDrive / SharePoint (connector)</h3>
        <form onSubmit={handleOneDriveSync} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <input
            placeholder="Drive ID"
            value={driveId}
            onChange={(e) => setDriveId(e.target.value)}
            style={{ borderRadius: 999, border: "1px solid #e6e6e6", padding: "8px 14px", flex: "1 1 220px" }}
          />
          <input
            placeholder="Folder path (e.g. Claims/2026/August)"
            value={folderPath}
            onChange={(e) => setFolderPath(e.target.value)}
            style={{ borderRadius: 999, border: "1px solid #e6e6e6", padding: "8px 14px", flex: "1 1 260px" }}
          />
          <button className="pill-button active" type="submit" disabled={syncing}>
            {syncing ? "Starting sync…" : "Sync Now"}
          </button>
        </form>
        {syncError && <div style={{ color: "#c0392b", fontSize: 13, marginTop: 10 }}>{syncError}</div>}
        <div style={{ fontSize: 12, color: "#888", marginTop: 10 }}>
          Requires an Azure app registration with admin consent — needs MS_TENANT_ID,
          MS_CLIENT_ID, and MS_CLIENT_SECRET configured on the backend. Use the link-sync
          method above if that's not set up yet.
        </div>
      </div>

      {error && <div style={{ color: "#c0392b", fontSize: 13, marginBottom: 12 }}>{error}</div>}
      <SourceFilesTable files={files} />
    </div>
  );
}
