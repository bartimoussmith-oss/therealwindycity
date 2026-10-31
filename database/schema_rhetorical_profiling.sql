PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS officials (
    official_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL UNIQUE,
    role_title TEXT NOT NULL,
    jurisdiction TEXT DEFAULT 'Cheyenne / Laramie County',
    ward_or_district TEXT,
    active_status INTEGER DEFAULT 1,
    rhetorical_baseline_json TEXT DEFAULT '{}',
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS governance_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    granicus_clip_id TEXT,
    meeting_date TEXT NOT NULL,
    committee_or_body TEXT NOT NULL,
    ordinance_or_res_num TEXT,
    title TEXT NOT NULL,
    category TEXT,
    attachment_sha256 TEXT UNIQUE,
    local_pdf_path TEXT,
    source_url TEXT,
    extracted_text TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS voting_record (
    vote_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    official_id INTEGER NOT NULL,
    vote_cast TEXT CHECK(vote_cast IN ('AYE', 'NAY', 'ABSTAIN', 'ABSENT', 'EXCUSED')),
    motion_role TEXT CHECK(motion_role IN ('MOVED', 'SECONDED', 'AMENDED', 'NONE')) DEFAULT 'NONE',
    stated_rationale TEXT,
    timestamp_offset TEXT,
    FOREIGN KEY (item_id) REFERENCES governance_items(item_id) ON DELETE CASCADE,
    FOREIGN KEY (official_id) REFERENCES officials(official_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS veracity_audit (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    official_id INTEGER NOT NULL,
    item_id INTEGER,
    statement_date TEXT NOT NULL,
    public_claim TEXT NOT NULL,
    statutory_fact TEXT NOT NULL,
    contradiction_type TEXT CHECK(contradiction_type IN (
        'STATUTORY_CONFLICT',
        'PRIOR_VOTE_REVERSAL',
        'BUDGET_DISCREPANCY',
        'PROCEDURAL_BYPASS',
        'OMISSION_OF_RECORD'
    )),
    severity_score INTEGER CHECK(severity_score BETWEEN 1 AND 10),
    rhetorical_tactic TEXT,
    evidence_citation TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (official_id) REFERENCES officials(official_id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES governance_items(item_id) ON DELETE SET NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS fts_forensic_archive USING fts5(
    record_type,
    reference_id UNINDEXED,
    primary_actor,
    title_or_claim,
    body_text,
    metadata_tags,
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS trg_sync_governance_fts
AFTER INSERT ON governance_items
BEGIN
    INSERT INTO fts_forensic_archive (record_type, reference_id, primary_actor, title_or_claim, body_text, metadata_tags)
    VALUES (
        'GOVERNANCE_ITEM',
        NEW.item_id,
        NEW.committee_or_body,
        NEW.title,
        COALESCE(NEW.extracted_text, ''),
        COALESCE(NEW.ordinance_or_res_num, '') || ' ' || COALESCE(NEW.category, '')
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_sync_veracity_fts
AFTER INSERT ON veracity_audit
BEGIN
    INSERT INTO fts_forensic_archive (record_type, reference_id, primary_actor, title_or_claim, body_text, metadata_tags)
    VALUES (
        'VERACITY_AUDIT',
        NEW.audit_id,
        (SELECT full_name FROM officials WHERE official_id = NEW.official_id),
        NEW.public_claim,
        NEW.statutory_fact || ' | Citation: ' || NEW.evidence_citation,
        NEW.contradiction_type || ' ' || COALESCE(NEW.rhetorical_tactic, '')
    );
END;
