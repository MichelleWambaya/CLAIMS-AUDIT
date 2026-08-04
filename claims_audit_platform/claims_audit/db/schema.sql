-- Claims Forensic Audit Platform — core schema
-- Reflects: merged dataset per session, OneDrive-sourced ingestion,
-- stored (not just downloaded) dashboards/presentations, audit trail,
-- config history.

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT UNIQUE NOT NULL,
    display_name    TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('analyst', 'admin')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One audit session = one merged working dataset an analyst is reviewing.
CREATE TABLE audit_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    created_by      UUID NOT NULL REFERENCES users(id),
    delta_link      TEXT,               -- Graph API delta token for incremental sync
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Each batch pulled in — from OneDrive/SharePoint via the Graph API
-- connector, not a manual browser upload. `source_ref` is the
-- drive-item id / webUrl so re-syncs can detect changed files.
CREATE TABLE source_files (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_session_id    UUID NOT NULL REFERENCES audit_sessions(id),
    source_type         TEXT NOT NULL CHECK (source_type IN ('onedrive', 'sharepoint', 'manual_upload')),
    source_ref          TEXT NOT NULL,       -- drive item id / path
    file_name           TEXT NOT NULL,
    sheet_name          TEXT,                -- selected sheet, if workbook
    extract_type        TEXT CHECK (extract_type IN ('claim_level', 'item_level')),
    row_count            BIGINT,
    status               TEXT NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending','parsing','parsed','error','merged')),
    schema_issues        JSONB,               -- per-file validation report, §4
    ingested_at          TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The merged, canonical row-level dataset for a session. Column-mapped
-- (§5.6) at ingest time so downstream rules never see raw headers.
-- Partitioned by audit_session_id in practice for large sessions.
CREATE TABLE claim_rows (
    id                  BIGSERIAL PRIMARY KEY,
    audit_session_id    UUID NOT NULL REFERENCES audit_sessions(id),
    source_file_id       UUID NOT NULL REFERENCES source_files(id),
    source_row_number    INT NOT NULL,        -- row within the original file
    member_id            TEXT,
    policy_number         TEXT,
    claim_code            TEXT,
    payer                 TEXT,
    category              TEXT,
    plan                  TEXT,
    claim_date            DATE,
    diagnosis_type        TEXT,
    diagnosis_name        TEXT,
    invoice_number        TEXT,
    amount                NUMERIC(14,2),
    provider              TEXT,
    product_name          TEXT,
    visit_date            DATE,
    item_status           TEXT,
    has_item_status_column BOOLEAN NOT NULL DEFAULT TRUE,
    raw_extra             JSONB                -- unmapped columns, preserved not dropped
);
CREATE INDEX idx_claim_rows_session ON claim_rows(audit_session_id);
CREATE INDEX idx_claim_rows_member ON claim_rows(audit_session_id, member_id);
CREATE INDEX idx_claim_rows_category ON claim_rows(audit_session_id, category);
CREATE INDEX idx_claim_rows_visit_date ON claim_rows(audit_session_id, visit_date);

-- One row per rule finding. `flag_type` matches the rule modules in rules/.
CREATE TABLE flags (
    id                  BIGSERIAL PRIMARY KEY,
    audit_session_id    UUID NOT NULL REFERENCES audit_sessions(id),
    flag_type           TEXT NOT NULL CHECK (flag_type IN (
                            'item_duplicate', 'claim_duplicate', 'non_payable',
                            'pricing_anomaly', 'invalid_member_policy', 'diagnosis_gap'
                         )),
    group_id             TEXT,                 -- duplicate cluster id, if applicable
    detail               JSONB NOT NULL,        -- similarity score, threshold used, matched keyword, etc.
    computed_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_flags_session_type ON flags(audit_session_id, flag_type);

-- Many-to-many: a flag can reference multiple claim_rows (duplicate clusters).
CREATE TABLE flag_rows (
    flag_id      BIGINT NOT NULL REFERENCES flags(id),
    claim_row_id BIGINT NOT NULL REFERENCES claim_rows(id),
    PRIMARY KEY (flag_id, claim_row_id)
);

-- Audit trail: analyst review state per flag.
CREATE TABLE flag_reviews (
    id           BIGSERIAL PRIMARY KEY,
    flag_id      BIGINT NOT NULL REFERENCES flags(id),
    reviewed_by  UUID NOT NULL REFERENCES users(id),
    status       TEXT NOT NULL CHECK (status IN ('confirmed', 'false_positive', 'needs_follow_up')),
    note         TEXT,
    reviewed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Non-payable override path (§5.2) — kept separate from the keyword
-- library so exceptions don't require editing detection rules.
CREATE TABLE flag_overrides (
    id             BIGSERIAL PRIMARY KEY,
    flag_id        BIGINT NOT NULL REFERENCES flags(id),
    approved_by    UUID NOT NULL REFERENCES users(id),
    justification  TEXT NOT NULL,   -- e.g. "prescribed for diagnosed deficiency, see attached note"
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Admin-editable thresholds (§5, §8) with change history.
CREATE TABLE rule_config (
    audit_session_id UUID PRIMARY KEY REFERENCES audit_sessions(id),
    config_json       JSONB NOT NULL,   -- serialized RuleConfig
    updated_by        UUID NOT NULL REFERENCES users(id),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE rule_config_history (
    id                BIGSERIAL PRIMARY KEY,
    audit_session_id  UUID NOT NULL REFERENCES audit_sessions(id),
    changed_by        UUID NOT NULL REFERENCES users(id),
    previous_json     JSONB NOT NULL,
    new_json          JSONB NOT NULL,
    changed_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Admin-editable column alias lists (§5.6), extendable without a deploy.
CREATE TABLE column_aliases (
    id              BIGSERIAL PRIMARY KEY,
    canonical_field TEXT NOT NULL,
    alias           TEXT NOT NULL,
    UNIQUE (canonical_field, alias)
);

-- Admin-editable non-payable keyword library (§5.2 seed data lives here).
CREATE TABLE non_payable_keywords (
    id          BIGSERIAL PRIMARY KEY,
    category    TEXT NOT NULL,
    keyword     TEXT NOT NULL,
    added_by    UUID REFERENCES users(id),
    added_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (category, keyword)
);

-- Saved dashboard/report configurations (filters, dims/measures, time range).
CREATE TABLE saved_views (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_session_id  UUID NOT NULL REFERENCES audit_sessions(id),
    created_by        UUID NOT NULL REFERENCES users(id),
    name              TEXT NOT NULL,
    view_config_json  JSONB NOT NULL,   -- time range preset, dims, measures, filters
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Generated reports/presentations are STORED (not just streamed for
-- one-time download), so past exports remain browsable.
CREATE TABLE generated_reports (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_session_id  UUID NOT NULL REFERENCES audit_sessions(id),
    saved_view_id      UUID REFERENCES saved_views(id),
    generated_by       UUID NOT NULL REFERENCES users(id),
    report_type        TEXT NOT NULL CHECK (report_type IN ('pptx', 'pdf', 'xlsx')),
    object_storage_key TEXT NOT NULL,    -- S3-compatible key
    status              TEXT NOT NULL DEFAULT 'queued'
                         CHECK (status IN ('queued', 'generating', 'ready', 'error')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    ready_at            TIMESTAMPTZ
);
CREATE INDEX idx_reports_session ON generated_reports(audit_session_id, created_at DESC);

-- Data-access audit log (health-claims data — required, §10).
CREATE TABLE access_log (
    id           BIGSERIAL PRIMARY KEY,
    user_id      UUID NOT NULL REFERENCES users(id),
    action       TEXT NOT NULL,          -- 'view_raw_member_data', 'export_report', etc.
    resource_ref TEXT,
    occurred_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
