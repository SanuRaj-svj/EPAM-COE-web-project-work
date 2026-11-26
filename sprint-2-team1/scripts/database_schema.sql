CREATE TABLE IF NOT EXISTS schema_metadata (
    metadata_key TEXT PRIMARY KEY,
    metadata_value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS specialties (
    specialty_id INTEGER PRIMARY KEY,
    specialty_code TEXT NOT NULL,
    specialty_name TEXT NOT NULL,
    UNIQUE (specialty_code, specialty_name)
);

CREATE TABLE IF NOT EXISTS packages (
    package_id INTEGER PRIMARY KEY,
    specialty_id INTEGER NOT NULL REFERENCES specialties(specialty_id),
    package_code TEXT NOT NULL,
    package_name TEXT NOT NULL,
    UNIQUE (specialty_id, package_code, package_name)
);

CREATE TABLE IF NOT EXISTS procedures (
    procedure_id INTEGER PRIMARY KEY,
    package_id INTEGER NOT NULL REFERENCES packages(package_id),
    procedure_code TEXT NOT NULL,
    procedure_name TEXT NOT NULL,
    tier3_price TEXT NOT NULL,
    tier2_price TEXT NOT NULL,
    tier1_price TEXT NOT NULL,
    stratification_remarks TEXT NOT NULL,
    implant_mapped TEXT NOT NULL DEFAULT '',
    implant_cost TEXT NOT NULL DEFAULT '',
    UNIQUE (
        package_id,
        procedure_code,
        procedure_name,
        tier3_price,
        tier2_price,
        tier1_price,
        stratification_remarks,
        implant_mapped,
        implant_cost
    ),
    UNIQUE (procedure_id, package_id)
);

CREATE TABLE IF NOT EXISTS procedure_source_occurrences (
    source_row_number INTEGER PRIMARY KEY CHECK (source_row_number > 0),
    procedure_id INTEGER NOT NULL REFERENCES procedures(procedure_id),
    source_page INTEGER NOT NULL CHECK (source_page > 0)
);

CREATE TABLE IF NOT EXISTS diagnoses (
    diagnosis_id INTEGER PRIMARY KEY,
    icd10_code TEXT NOT NULL COLLATE NOCASE UNIQUE,
    diagnosis_name TEXT NOT NULL,
    source_reference TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS diagnosis_synonyms (
    synonym_id INTEGER PRIMARY KEY,
    diagnosis_id INTEGER NOT NULL REFERENCES diagnoses(diagnosis_id),
    synonym_text TEXT NOT NULL COLLATE NOCASE,
    UNIQUE (diagnosis_id, synonym_text)
);

CREATE TABLE IF NOT EXISTS diagnosis_package_mapping (
    mapping_id INTEGER PRIMARY KEY,
    diagnosis_id INTEGER NOT NULL REFERENCES diagnoses(diagnosis_id),
    package_id INTEGER NOT NULL REFERENCES packages(package_id),
    procedure_id INTEGER NOT NULL,
    validation_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (validation_status IN ('pending', 'approved', 'rejected')),
    evidence_source TEXT NOT NULL DEFAULT '',
    rationale TEXT NOT NULL DEFAULT '',
    reviewed_by TEXT NOT NULL DEFAULT '',
    reviewed_at TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (procedure_id, package_id)
        REFERENCES procedures(procedure_id, package_id),
    UNIQUE (diagnosis_id, package_id, procedure_id),
    CHECK (
        validation_status != 'approved'
        OR (
            length(trim(evidence_source)) > 0
            AND length(trim(rationale)) > 0
            AND length(trim(reviewed_by)) > 0
            AND length(trim(reviewed_at)) > 0
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_packages_code
    ON packages(package_code);
CREATE INDEX IF NOT EXISTS idx_procedures_code
    ON procedures(procedure_code);
CREATE INDEX IF NOT EXISTS idx_mapping_diagnosis
    ON diagnosis_package_mapping(diagnosis_id);
CREATE INDEX IF NOT EXISTS idx_mapping_package
    ON diagnosis_package_mapping(package_id);

CREATE VIEW IF NOT EXISTS diagnosis_procedure_package AS
SELECT
    mapping.mapping_id,
    mapping.validation_status,
    diagnosis.icd10_code,
    diagnosis.diagnosis_name,
    specialty.specialty_code,
    specialty.specialty_name,
    package.package_code,
    package.package_name,
    procedure.procedure_code,
    procedure.procedure_name,
    mapping.evidence_source,
    mapping.rationale,
    mapping.reviewed_by,
    mapping.reviewed_at
FROM diagnosis_package_mapping AS mapping
JOIN diagnoses AS diagnosis
    ON diagnosis.diagnosis_id = mapping.diagnosis_id
JOIN packages AS package
    ON package.package_id = mapping.package_id
JOIN specialties AS specialty
    ON specialty.specialty_id = package.specialty_id
JOIN procedures AS procedure
    ON procedure.procedure_id = mapping.procedure_id
    AND procedure.package_id = mapping.package_id;

CREATE TABLE IF NOT EXISTS package_eligibility (
    id INTEGER PRIMARY KEY,
    package_id INTEGER NOT NULL REFERENCES packages(package_id),
    rule_type TEXT NOT NULL DEFAULT 'clinical',
    rule_text TEXT NOT NULL,
    required INTEGER NOT NULL DEFAULT 0 CHECK (required IN (0, 1)),
    source_document TEXT NOT NULL DEFAULT 'HBP_2022.pdf',
    source_page INTEGER,
    notes TEXT NOT NULL DEFAULT '',
    UNIQUE (package_id, rule_type, rule_text)
);

CREATE TABLE IF NOT EXISTS package_preauth_rules (
    id INTEGER PRIMARY KEY,
    package_id INTEGER NOT NULL REFERENCES packages(package_id),
    preauth_required TEXT NOT NULL DEFAULT 'unknown'
        CHECK (preauth_required IN ('unknown', 'mandatory', 'conditional', 'not_required')),
    preauth_type TEXT NOT NULL DEFAULT 'unknown'
        CHECK (preauth_type IN ('unknown', 'mandatory', 'conditional', 'not_required')),
    requirement_text TEXT NOT NULL DEFAULT '',
    required_documents TEXT NOT NULL DEFAULT '',
    source_document TEXT NOT NULL DEFAULT 'HBP_2022.pdf',
    source_page INTEGER,
    notes TEXT NOT NULL DEFAULT '',
    UNIQUE (package_id)
);

CREATE TABLE IF NOT EXISTS investigations (
    investigation_id INTEGER PRIMARY KEY,
    investigation_name TEXT NOT NULL UNIQUE,
    investigation_type TEXT NOT NULL DEFAULT 'other'
);

CREATE TABLE IF NOT EXISTS package_investigations (
    id INTEGER PRIMARY KEY,
    package_id INTEGER NOT NULL REFERENCES packages(package_id),
    investigation_id INTEGER NOT NULL REFERENCES investigations(investigation_id),
    investigation_name TEXT NOT NULL DEFAULT '',
    investigation_type TEXT NOT NULL DEFAULT 'other',
    mandatory INTEGER NOT NULL DEFAULT 0 CHECK (mandatory IN (0, 1)),
    timing TEXT NOT NULL DEFAULT '',
    requirement_text TEXT NOT NULL,
    source_document TEXT NOT NULL DEFAULT 'HBP_2022.pdf',
    source_page INTEGER,
    notes TEXT NOT NULL DEFAULT '',
    UNIQUE (package_id, investigation_id, requirement_text)
);

CREATE TABLE IF NOT EXISTS documents (
    document_id INTEGER PRIMARY KEY,
    document_name TEXT NOT NULL UNIQUE,
    document_type TEXT NOT NULL DEFAULT 'other'
);

CREATE TABLE IF NOT EXISTS package_documents (
    id INTEGER PRIMARY KEY,
    package_id INTEGER NOT NULL REFERENCES packages(package_id),
    document_id INTEGER NOT NULL REFERENCES documents(document_id),
    document_name TEXT NOT NULL DEFAULT '',
    document_type TEXT NOT NULL DEFAULT 'other',
    mandatory INTEGER NOT NULL DEFAULT 0 CHECK (mandatory IN (0, 1)),
    requirement_text TEXT NOT NULL,
    source_document TEXT NOT NULL DEFAULT 'HBP_2022.pdf',
    source_page INTEGER,
    notes TEXT NOT NULL DEFAULT '',
    UNIQUE (package_id, document_id, requirement_text)
);

CREATE INDEX IF NOT EXISTS idx_eligibility_package
    ON package_eligibility(package_id);
CREATE INDEX IF NOT EXISTS idx_preauth_package
    ON package_preauth_rules(package_id);
CREATE INDEX IF NOT EXISTS idx_package_investigations_package
    ON package_investigations(package_id);
CREATE INDEX IF NOT EXISTS idx_package_documents_package
    ON package_documents(package_id);

CREATE TABLE IF NOT EXISTS review_items (
    review_id INTEGER PRIMARY KEY,
    area TEXT NOT NULL CHECK (area IN (
        'procedure_code', 'preauthorization', 'investigation',
        'supporting_document', 'icd10'
    )),
    item_key TEXT NOT NULL,
    source_document TEXT NOT NULL DEFAULT 'HBP_2022.pdf',
    source_page INTEGER,
    source_context TEXT NOT NULL DEFAULT '',
    candidate_status TEXT NOT NULL DEFAULT 'unknown',
    review_status TEXT NOT NULL DEFAULT 'pending',
    reviewer TEXT NOT NULL DEFAULT '',
    reviewed_at TEXT NOT NULL DEFAULT '',
    review_notes TEXT NOT NULL DEFAULT '',
    UNIQUE (area, item_key)
);

CREATE TABLE IF NOT EXISTS review_history (
    history_id INTEGER PRIMARY KEY,
    review_id INTEGER NOT NULL REFERENCES review_items(review_id),
    previous_status TEXT NOT NULL DEFAULT '',
    new_status TEXT NOT NULL,
    reviewer TEXT NOT NULL DEFAULT '',
    reviewed_at TEXT NOT NULL,
    review_notes TEXT NOT NULL DEFAULT '',
    source_document TEXT NOT NULL DEFAULT 'HBP_2022.pdf',
    source_page INTEGER
);

CREATE TABLE IF NOT EXISTS approved_review_changes (
    change_id INTEGER PRIMARY KEY,
    review_id INTEGER NOT NULL REFERENCES review_items(review_id),
    area TEXT NOT NULL,
    item_key TEXT NOT NULL,
    change_payload TEXT NOT NULL,
    approved_at TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT '',
    UNIQUE (area, item_key)
);
