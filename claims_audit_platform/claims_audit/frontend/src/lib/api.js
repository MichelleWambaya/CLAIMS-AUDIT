const BASE = "/api";

function authHeaders() {
  const token = localStorage.getItem("aar_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(path, options = {}) {
  const resp = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...authHeaders(), ...options.headers },
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`${resp.status} ${resp.statusText}: ${body}`);
  }
  return resp.json();
}

export const api = {
  login: (email, password) => {
    const form = new URLSearchParams({ username: email, password });
    return fetch(`${BASE}/auth/login`, { method: "POST", body: form }).then((r) => r.json());
  },
  listSessions: () => request("/sessions"),
  createSession: (name) => request("/sessions", { method: "POST", body: JSON.stringify({ name }) }),
  triggerSync: (sessionId, driveId, folderPath) =>
    request(`/sessions/${sessionId}/sync`, {
      method: "POST",
      body: JSON.stringify({ drive_id: driveId, folder_path: folderPath }),
    }),
  listSourceFiles: (sessionId) => request(`/sessions/${sessionId}/source-files`),
  recomputeFlags: (sessionId) => request(`/sessions/${sessionId}/flags/recompute`, { method: "POST" }),
  listFlags: (sessionId, { flagType, limit = 50, offset = 0 } = {}) => {
    const params = new URLSearchParams({ limit, offset });
    if (flagType) params.set("flag_type", flagType);
    return request(`/sessions/${sessionId}/flags?${params.toString()}`);
  },
  reviewFlag: (sessionId, flagId, status, note) =>
    request(`/sessions/${sessionId}/flags/${flagId}/review`, {
      method: "POST",
      body: JSON.stringify({ status, note }),
    }),
  overrideFlag: (sessionId, flagId, justification) =>
    request(`/sessions/${sessionId}/flags/${flagId}/override`, {
      method: "POST",
      body: JSON.stringify({ justification }),
    }),
  requestReport: (sessionId, reportType, savedViewId) =>
    request(`/sessions/${sessionId}/reports`, {
      method: "POST",
      body: JSON.stringify({ report_type: reportType, saved_view_id: savedViewId }),
    }),
  listReports: (sessionId) => request(`/sessions/${sessionId}/reports`),
  getReportStatus: (sessionId, reportId) => request(`/sessions/${sessionId}/reports/${reportId}`),
  saveView: (sessionId, name, viewConfig) =>
    request(`/sessions/${sessionId}/saved-views`, {
      method: "POST",
      body: JSON.stringify({ name, view_config: viewConfig }),
    }),
  listSavedViews: (sessionId) => request(`/sessions/${sessionId}/saved-views`),
};
