PRAGMA foreign_keys = ON;
PRAGMA application_id = 1262634032;
PRAGMA user_version = 1;

CREATE TABLE kb_release (
    release_id TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    contract_version TEXT NOT NULL,
    dataset_version TEXT NOT NULL UNIQUE,
    build_manifest_sha256 TEXT NOT NULL CHECK (length(build_manifest_sha256) = 64),
    source_bundle_sha256 TEXT NOT NULL CHECK (length(source_bundle_sha256) = 64),
    release_status TEXT NOT NULL CHECK (release_status IN ('DRAFT', 'HUMAN_APPROVED', 'RETIRED')),
    approved_by TEXT,
    approved_at_utc TEXT,
    built_at_utc TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    CHECK (
        release_status <> 'HUMAN_APPROVED'
        OR (
            length(trim(approved_by)) > 0
            AND approved_at_utc GLOB '????-??-??T??:??:??Z'
        )
    )
) STRICT;

CREATE TABLE kb_entity (
    entity_key TEXT PRIMARY KEY CHECK (entity_key GLOB 'kb:*'),
    entity_type TEXT NOT NULL CHECK (entity_type IN (
        'paper', 'source_reference', 'organism', 'tissue', 'experiment',
        'design_case', 'construct', 'transcription_unit', 'component',
        'component_evidence', 'metabolite', 'measurement', 'accession',
        'evidence_claim', 'evidence_level', 'applicability_scope', 'limitation'
    )),
    canonical_label TEXT NOT NULL,
    lifecycle_status TEXT NOT NULL CHECK (
        lifecycle_status IN ('ACTIVE', 'SUPERSEDED', 'RETIRED', 'WITHDRAWN')
    ),
    current_revision INTEGER NOT NULL CHECK (current_revision >= 1),
    created_by TEXT NOT NULL,
    created_by_actor_type TEXT NOT NULL CHECK (created_by_actor_type IN ('HUMAN', 'IMPORT', 'AI')),
    created_at_utc TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
) STRICT;

CREATE INDEX idx_kb_entity_type_status
ON kb_entity(entity_type, lifecycle_status, entity_key);

CREATE TABLE kb_entity_revision (
    entity_key TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    release_id TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    change_reason TEXT NOT NULL,
    supersedes_revision INTEGER,
    created_by TEXT NOT NULL,
    created_by_actor_type TEXT NOT NULL CHECK (created_by_actor_type IN ('HUMAN', 'IMPORT', 'AI')),
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY (entity_key, revision),
    FOREIGN KEY (entity_key) REFERENCES kb_entity(entity_key),
    FOREIGN KEY (release_id) REFERENCES kb_release(release_id),
    FOREIGN KEY (entity_key, supersedes_revision) REFERENCES kb_entity_revision(entity_key, revision),
    CHECK (
        (revision = 1 AND supersedes_revision IS NULL)
        OR (revision > 1 AND supersedes_revision = revision - 1)
    )
) STRICT;

CREATE TABLE kb_paper (
    paper_key TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    publication_year INTEGER CHECK (publication_year IS NULL OR publication_year BETWEEN 1600 AND 3000),
    journal_or_repository TEXT NOT NULL,
    doi_normalized TEXT,
    pmid TEXT,
    pmcid TEXT,
    publication_status TEXT NOT NULL CHECK (
        publication_status IN ('PUBLISHED', 'PREPRINT', 'THESIS', 'DATASET', 'UNKNOWN')
    ),
    FOREIGN KEY (paper_key) REFERENCES kb_entity(entity_key)
) STRICT;
CREATE UNIQUE INDEX uq_kb_paper_doi ON kb_paper(doi_normalized) WHERE doi_normalized IS NOT NULL;
CREATE UNIQUE INDEX uq_kb_paper_pmid ON kb_paper(pmid) WHERE pmid IS NOT NULL;

CREATE TABLE kb_source_reference (
    source_reference_key TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL CHECK (source_kind IN (
        'PAPER', 'DATABASE_RECORD', 'DATASET', 'FILE', 'WEB_SNAPSHOT',
        'INTERNAL_REVIEW_NOTE', 'USER_PROVIDED'
    )),
    provider TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_version TEXT NOT NULL,
    source_uri TEXT NOT NULL,
    source_title TEXT NOT NULL,
    content_sha256 TEXT CHECK (content_sha256 IS NULL OR length(content_sha256) = 64),
    license_or_access_status TEXT NOT NULL,
    acquired_at_utc TEXT,
    immutable_identity_sha256 TEXT NOT NULL CHECK (length(immutable_identity_sha256) = 64),
    paper_key TEXT,
    FOREIGN KEY (source_reference_key) REFERENCES kb_entity(entity_key),
    FOREIGN KEY (paper_key) REFERENCES kb_paper(paper_key),
    UNIQUE (provider, source_record_id, source_version)
) STRICT;

CREATE TABLE kb_organism (
    organism_key TEXT PRIMARY KEY,
    scientific_name TEXT NOT NULL,
    taxonomy_id TEXT,
    strain_cultivar_ecotype TEXT NOT NULL,
    common_name TEXT NOT NULL,
    FOREIGN KEY (organism_key) REFERENCES kb_entity(entity_key),
    UNIQUE (taxonomy_id, strain_cultivar_ecotype)
) STRICT;

CREATE TABLE kb_tissue (
    tissue_key TEXT PRIMARY KEY,
    organism_key TEXT,
    tissue_name TEXT NOT NULL,
    ontology_id TEXT,
    developmental_stage TEXT NOT NULL,
    FOREIGN KEY (tissue_key) REFERENCES kb_entity(entity_key),
    FOREIGN KEY (organism_key) REFERENCES kb_organism(organism_key),
    UNIQUE (organism_key, tissue_name, developmental_stage)
) STRICT;

CREATE TABLE kb_experiment (
    experiment_key TEXT PRIMARY KEY,
    paper_key TEXT,
    experiment_label TEXT NOT NULL,
    experiment_type TEXT NOT NULL,
    organism_key TEXT,
    tissue_key TEXT,
    developmental_stage TEXT NOT NULL,
    genotype_or_background TEXT NOT NULL,
    treatment_context TEXT NOT NULL,
    assay_context TEXT NOT NULL,
    condition_json TEXT NOT NULL CHECK (json_valid(condition_json)),
    context_completeness TEXT NOT NULL CHECK (context_completeness IN ('COMPLETE', 'PARTIAL', 'UNKNOWN')),
    FOREIGN KEY (experiment_key) REFERENCES kb_entity(entity_key),
    FOREIGN KEY (paper_key) REFERENCES kb_paper(paper_key),
    FOREIGN KEY (organism_key) REFERENCES kb_organism(organism_key),
    FOREIGN KEY (tissue_key) REFERENCES kb_tissue(tissue_key)
) STRICT;

CREATE TABLE kb_design_case (
    design_case_key TEXT PRIMARY KEY,
    case_label TEXT NOT NULL,
    case_type TEXT NOT NULL CHECK (
        case_type IN ('PUBLISHED_CASE', 'RECONSTRUCTED_CASE', 'INTERNAL_REVIEW_CASE', 'UNKNOWN')
    ),
    case_summary TEXT NOT NULL,
    review_boundary TEXT NOT NULL,
    FOREIGN KEY (design_case_key) REFERENCES kb_entity(entity_key)
) STRICT;

CREATE TABLE kb_construct (
    construct_key TEXT PRIMARY KEY,
    construct_label TEXT NOT NULL,
    construct_type TEXT NOT NULL,
    topology TEXT NOT NULL CHECK (topology IN ('LINEAR', 'CIRCULAR', 'UNKNOWN')),
    sequence_availability TEXT NOT NULL CHECK (
        sequence_availability IN ('COMPLETE', 'PARTIAL', 'ACCESSION_ONLY', 'NOT_AVAILABLE', 'UNKNOWN')
    ),
    sequence_sha256 TEXT CHECK (sequence_sha256 IS NULL OR length(sequence_sha256) = 64),
    sequence_length INTEGER CHECK (sequence_length IS NULL OR sequence_length >= 0),
    source_reference_key TEXT,
    FOREIGN KEY (construct_key) REFERENCES kb_entity(entity_key),
    FOREIGN KEY (source_reference_key) REFERENCES kb_source_reference(source_reference_key),
    CHECK (sequence_availability <> 'COMPLETE' OR (sequence_sha256 IS NOT NULL AND sequence_length IS NOT NULL))
) STRICT;

CREATE TABLE kb_transcription_unit (
    transcription_unit_key TEXT PRIMARY KEY,
    construct_key TEXT NOT NULL,
    unit_label TEXT NOT NULL,
    unit_order INTEGER NOT NULL CHECK (unit_order >= 1),
    orientation TEXT NOT NULL CHECK (orientation IN ('FORWARD', 'REVERSE', 'UNKNOWN')),
    sequence_sha256 TEXT CHECK (sequence_sha256 IS NULL OR length(sequence_sha256) = 64),
    sequence_length INTEGER CHECK (sequence_length IS NULL OR sequence_length >= 0),
    FOREIGN KEY (transcription_unit_key) REFERENCES kb_entity(entity_key),
    FOREIGN KEY (construct_key) REFERENCES kb_construct(construct_key),
    UNIQUE (construct_key, unit_order),
    UNIQUE (construct_key, unit_label)
) STRICT;

CREATE TABLE kb_component (
    component_key TEXT PRIMARY KEY,
    component_name TEXT NOT NULL,
    component_type TEXT NOT NULL CHECK (component_type IN (
        'PROMOTER', 'FIVE_PRIME_UTR', 'CDS', 'THREE_PRIME_REGULATORY_REGION',
        'TERMINATOR', 'SIGNAL_PEPTIDE', 'TRANSIT_PEPTIDE', 'TAG', 'LINKER',
        'MARKER', 'REPORTER', 'VECTOR_BACKBONE', 'ORIGIN', 'BORDER', 'OTHER', 'UNKNOWN'
    )),
    source_organism_key TEXT,
    sequence_availability TEXT NOT NULL CHECK (
        sequence_availability IN ('COMPLETE', 'PARTIAL', 'ACCESSION_ONLY', 'NOT_AVAILABLE', 'UNKNOWN')
    ),
    sequence_sha256 TEXT CHECK (sequence_sha256 IS NULL OR length(sequence_sha256) = 64),
    sequence_length INTEGER CHECK (sequence_length IS NULL OR sequence_length >= 0),
    source_reference_key TEXT,
    FOREIGN KEY (component_key) REFERENCES kb_entity(entity_key),
    FOREIGN KEY (source_organism_key) REFERENCES kb_organism(organism_key),
    FOREIGN KEY (source_reference_key) REFERENCES kb_source_reference(source_reference_key),
    CHECK (sequence_availability <> 'COMPLETE' OR (sequence_sha256 IS NOT NULL AND sequence_length IS NOT NULL))
) STRICT;

CREATE TABLE kb_transcription_unit_component (
    transcription_unit_key TEXT NOT NULL,
    component_key TEXT NOT NULL,
    component_order INTEGER NOT NULL CHECK (component_order >= 1),
    biological_role TEXT NOT NULL,
    orientation TEXT NOT NULL CHECK (orientation IN ('FORWARD', 'REVERSE', 'UNKNOWN')),
    start_zero_based INTEGER CHECK (start_zero_based IS NULL OR start_zero_based >= 0),
    end_zero_based_exclusive INTEGER CHECK (end_zero_based_exclusive IS NULL OR end_zero_based_exclusive >= 0),
    PRIMARY KEY (transcription_unit_key, component_order),
    FOREIGN KEY (transcription_unit_key) REFERENCES kb_transcription_unit(transcription_unit_key),
    FOREIGN KEY (component_key) REFERENCES kb_component(component_key),
    CHECK (
        (start_zero_based IS NULL AND end_zero_based_exclusive IS NULL)
        OR (start_zero_based IS NOT NULL AND end_zero_based_exclusive > start_zero_based)
    )
) STRICT;

CREATE TABLE kb_design_case_paper (
    design_case_key TEXT NOT NULL,
    paper_key TEXT NOT NULL,
    relationship_type TEXT NOT NULL CHECK (
        relationship_type IN ('PRIMARY_REPORT', 'SUPPORTING_REPORT', 'REVIEW', 'CONFLICTING_REPORT')
    ),
    PRIMARY KEY (design_case_key, paper_key, relationship_type),
    FOREIGN KEY (design_case_key) REFERENCES kb_design_case(design_case_key),
    FOREIGN KEY (paper_key) REFERENCES kb_paper(paper_key)
) STRICT;

CREATE TABLE kb_design_case_experiment (
    design_case_key TEXT NOT NULL,
    experiment_key TEXT NOT NULL,
    relationship_type TEXT NOT NULL CHECK (relationship_type IN ('PRIMARY', 'SUPPORTING', 'COMPARATOR', 'CONFLICTING')),
    PRIMARY KEY (design_case_key, experiment_key),
    FOREIGN KEY (design_case_key) REFERENCES kb_design_case(design_case_key),
    FOREIGN KEY (experiment_key) REFERENCES kb_experiment(experiment_key)
) STRICT;

CREATE TABLE kb_design_case_construct (
    design_case_key TEXT NOT NULL,
    construct_key TEXT NOT NULL,
    relationship_type TEXT NOT NULL CHECK (relationship_type IN ('TESTED', 'RECONSTRUCTED', 'REFERENCE', 'COMPARATOR')),
    PRIMARY KEY (design_case_key, construct_key),
    FOREIGN KEY (design_case_key) REFERENCES kb_design_case(design_case_key),
    FOREIGN KEY (construct_key) REFERENCES kb_construct(construct_key)
) STRICT;

CREATE TABLE kb_accession (
    accession_key TEXT PRIMARY KEY,
    accession_system TEXT NOT NULL,
    accession_value TEXT NOT NULL,
    accession_version TEXT NOT NULL,
    record_type TEXT NOT NULL,
    source_reference_key TEXT NOT NULL,
    referenced_entity_key TEXT,
    FOREIGN KEY (accession_key) REFERENCES kb_entity(entity_key),
    FOREIGN KEY (source_reference_key) REFERENCES kb_source_reference(source_reference_key),
    FOREIGN KEY (referenced_entity_key) REFERENCES kb_entity(entity_key),
    UNIQUE (accession_system, accession_value, accession_version)
) STRICT;

CREATE TABLE kb_metabolite (
    metabolite_key TEXT PRIMARY KEY,
    preferred_name TEXT NOT NULL,
    chebi_id TEXT,
    inchikey TEXT,
    formula TEXT NOT NULL,
    FOREIGN KEY (metabolite_key) REFERENCES kb_entity(entity_key)
) STRICT;
CREATE UNIQUE INDEX uq_kb_metabolite_chebi ON kb_metabolite(chebi_id) WHERE chebi_id IS NOT NULL;
CREATE UNIQUE INDEX uq_kb_metabolite_inchikey ON kb_metabolite(inchikey) WHERE inchikey IS NOT NULL;

CREATE TABLE kb_measurement (
    measurement_key TEXT PRIMARY KEY,
    experiment_key TEXT NOT NULL,
    metabolite_key TEXT,
    measured_entity_key TEXT,
    measurement_type TEXT NOT NULL,
    value_numeric REAL,
    value_text TEXT,
    unit TEXT NOT NULL,
    uncertainty_numeric REAL,
    replicate_count INTEGER CHECK (replicate_count IS NULL OR replicate_count >= 0),
    normalization_basis TEXT NOT NULL,
    timepoint TEXT NOT NULL,
    source_reference_key TEXT NOT NULL,
    FOREIGN KEY (measurement_key) REFERENCES kb_entity(entity_key),
    FOREIGN KEY (experiment_key) REFERENCES kb_experiment(experiment_key),
    FOREIGN KEY (metabolite_key) REFERENCES kb_metabolite(metabolite_key),
    FOREIGN KEY (measured_entity_key) REFERENCES kb_entity(entity_key),
    FOREIGN KEY (source_reference_key) REFERENCES kb_source_reference(source_reference_key),
    CHECK (value_numeric IS NOT NULL OR value_text IS NOT NULL)
) STRICT;

CREATE TABLE kb_evidence_level (
    evidence_level_key TEXT PRIMARY KEY,
    level_code TEXT NOT NULL UNIQUE,
    rank_ordinal INTEGER NOT NULL CHECK (rank_ordinal >= 0),
    definition TEXT NOT NULL,
    minimum_source_requirements TEXT NOT NULL,
    permits_runtime_use INTEGER NOT NULL CHECK (permits_runtime_use IN (0, 1)),
    permits_registry_consideration INTEGER NOT NULL CHECK (permits_registry_consideration IN (0, 1)),
    FOREIGN KEY (evidence_level_key) REFERENCES kb_entity(entity_key),
    CHECK (permits_registry_consideration = 0 OR permits_runtime_use = 1)
) STRICT;

CREATE TABLE kb_evidence_claim (
    evidence_claim_key TEXT PRIMARY KEY,
    subject_entity_key TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_entity_key TEXT,
    object_value_text TEXT,
    object_value_json TEXT CHECK (object_value_json IS NULL OR json_valid(object_value_json)),
    value_unit TEXT NOT NULL,
    fact_class TEXT NOT NULL CHECK (fact_class IN ('FACT', 'DERIVATION', 'INFERENCE', 'UNKNOWN')),
    provenance_method TEXT NOT NULL,
    evidence_type TEXT NOT NULL,
    evidence_level_key TEXT NOT NULL,
    organism_context_status TEXT NOT NULL CHECK (organism_context_status IN ('KNOWN', 'UNKNOWN', 'NOT_APPLICABLE')),
    organism_key TEXT,
    tissue_context_status TEXT NOT NULL CHECK (tissue_context_status IN ('KNOWN', 'UNKNOWN', 'NOT_APPLICABLE')),
    tissue_key TEXT,
    experiment_context_status TEXT NOT NULL CHECK (experiment_context_status IN ('KNOWN', 'UNKNOWN', 'NOT_APPLICABLE')),
    experiment_key TEXT,
    unknown_reason TEXT NOT NULL,
    review_status TEXT NOT NULL CHECK (review_status IN (
        'UNREVIEWED', 'PENDING_HUMAN_REVIEW', 'HUMAN_APPROVED',
        'HUMAN_REJECTED', 'SUPERSEDED', 'RETIRED'
    )),
    reviewed_by TEXT,
    reviewed_at_utc TEXT,
    runtime_eligible INTEGER NOT NULL CHECK (runtime_eligible IN (0, 1)),
    registry_eligible INTEGER NOT NULL CHECK (registry_eligible IN (0, 1)),
    eligibility_actor_type TEXT NOT NULL CHECK (eligibility_actor_type IN ('NONE', 'HUMAN')),
    eligibility_decided_by TEXT,
    eligibility_decided_at_utc TEXT,
    registry_candidate_reason TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_by_actor_type TEXT NOT NULL CHECK (created_by_actor_type IN ('HUMAN', 'IMPORT', 'AI')),
    created_at_utc TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    FOREIGN KEY (evidence_claim_key) REFERENCES kb_entity(entity_key),
    FOREIGN KEY (subject_entity_key) REFERENCES kb_entity(entity_key),
    FOREIGN KEY (object_entity_key) REFERENCES kb_entity(entity_key),
    FOREIGN KEY (evidence_level_key) REFERENCES kb_evidence_level(evidence_level_key),
    FOREIGN KEY (organism_key) REFERENCES kb_organism(organism_key),
    FOREIGN KEY (tissue_key) REFERENCES kb_tissue(tissue_key),
    FOREIGN KEY (experiment_key) REFERENCES kb_experiment(experiment_key),
    CHECK (
        (organism_context_status = 'KNOWN' AND organism_key IS NOT NULL)
        OR (organism_context_status <> 'KNOWN' AND organism_key IS NULL)
    ),
    CHECK (
        (tissue_context_status = 'KNOWN' AND tissue_key IS NOT NULL)
        OR (tissue_context_status <> 'KNOWN' AND tissue_key IS NULL)
    ),
    CHECK (
        (experiment_context_status = 'KNOWN' AND experiment_key IS NOT NULL)
        OR (experiment_context_status <> 'KNOWN' AND experiment_key IS NULL)
    ),
    CHECK (
        (fact_class = 'UNKNOWN'
            AND object_entity_key IS NULL
            AND object_value_text IS NULL
            AND object_value_json IS NULL
            AND length(trim(unknown_reason)) > 0)
        OR
        (fact_class <> 'UNKNOWN'
            AND ((object_entity_key IS NOT NULL) + (object_value_text IS NOT NULL) + (object_value_json IS NOT NULL)) = 1)
    ),
    CHECK (
        review_status <> 'HUMAN_APPROVED'
        OR (length(trim(reviewed_by)) > 0 AND reviewed_at_utc IS NOT NULL)
    ),
    CHECK (
        runtime_eligible = 0
        OR (
            fact_class = 'FACT'
            AND review_status = 'HUMAN_APPROVED'
            AND eligibility_actor_type = 'HUMAN'
            AND length(trim(eligibility_decided_by)) > 0
            AND eligibility_decided_at_utc IS NOT NULL
        )
    ),
    CHECK (
        registry_eligible = 0
        OR (
            runtime_eligible = 1
            AND eligibility_actor_type = 'HUMAN'
            AND length(trim(registry_candidate_reason)) > 0
        )
    )
) STRICT;
CREATE INDEX idx_kb_claim_subject ON kb_evidence_claim(subject_entity_key, predicate, review_status);
CREATE INDEX idx_kb_claim_context ON kb_evidence_claim(organism_key, tissue_key, experiment_key);
CREATE INDEX idx_kb_claim_runtime ON kb_evidence_claim(runtime_eligible, registry_eligible, fact_class, review_status);

CREATE TABLE kb_claim_source (
    evidence_claim_key TEXT NOT NULL,
    source_reference_key TEXT NOT NULL,
    source_role TEXT NOT NULL CHECK (source_role IN ('PRIMARY', 'SUPPORTING', 'CONFLICTING', 'DERIVATION_INPUT')),
    location_type TEXT NOT NULL CHECK (location_type IN (
        'PAGE', 'SECTION', 'FIGURE', 'TABLE', 'SUPPLEMENT', 'ACCESSION_FEATURE',
        'COORDINATE', 'JSON_POINTER', 'FILE_OFFSET', 'WHOLE_RECORD', 'UNKNOWN'
    )),
    location_value TEXT NOT NULL,
    source_excerpt_sha256 TEXT CHECK (source_excerpt_sha256 IS NULL OR length(source_excerpt_sha256) = 64),
    PRIMARY KEY (evidence_claim_key, source_reference_key, source_role, location_type, location_value),
    FOREIGN KEY (evidence_claim_key) REFERENCES kb_evidence_claim(evidence_claim_key),
    FOREIGN KEY (source_reference_key) REFERENCES kb_source_reference(source_reference_key),
    CHECK (location_type <> 'UNKNOWN' OR length(trim(location_value)) > 0)
) STRICT;

CREATE TABLE kb_component_evidence (
    component_evidence_key TEXT PRIMARY KEY,
    component_key TEXT NOT NULL,
    evidence_claim_key TEXT NOT NULL,
    evidence_role TEXT NOT NULL CHECK (
        evidence_role IN ('IDENTITY', 'BOUNDARY', 'FUNCTION', 'EXPERIMENTAL_CONTEXT', 'LIMITATION')
    ),
    created_at_utc TEXT NOT NULL,
    FOREIGN KEY (component_evidence_key) REFERENCES kb_entity(entity_key),
    FOREIGN KEY (component_key) REFERENCES kb_component(component_key),
    FOREIGN KEY (evidence_claim_key) REFERENCES kb_evidence_claim(evidence_claim_key),
    UNIQUE (component_key, evidence_claim_key, evidence_role)
) STRICT;

CREATE TABLE kb_applicability_scope (
    applicability_scope_key TEXT PRIMARY KEY,
    scope_mode TEXT NOT NULL CHECK (scope_mode IN ('INCLUDE', 'EXCLUDE')),
    organism_key TEXT,
    tissue_key TEXT,
    experiment_key TEXT,
    developmental_stage TEXT NOT NULL,
    condition_json TEXT NOT NULL CHECK (json_valid(condition_json)),
    scope_note TEXT NOT NULL,
    FOREIGN KEY (applicability_scope_key) REFERENCES kb_entity(entity_key),
    FOREIGN KEY (organism_key) REFERENCES kb_organism(organism_key),
    FOREIGN KEY (tissue_key) REFERENCES kb_tissue(tissue_key),
    FOREIGN KEY (experiment_key) REFERENCES kb_experiment(experiment_key),
    CHECK (
        organism_key IS NOT NULL OR tissue_key IS NOT NULL OR experiment_key IS NOT NULL
        OR developmental_stage <> '' OR condition_json <> '{}'
    )
) STRICT;

CREATE TABLE kb_claim_applicability_scope (
    evidence_claim_key TEXT NOT NULL,
    applicability_scope_key TEXT NOT NULL,
    PRIMARY KEY (evidence_claim_key, applicability_scope_key),
    FOREIGN KEY (evidence_claim_key) REFERENCES kb_evidence_claim(evidence_claim_key),
    FOREIGN KEY (applicability_scope_key) REFERENCES kb_applicability_scope(applicability_scope_key)
) STRICT;

CREATE TABLE kb_limitation (
    limitation_key TEXT PRIMARY KEY,
    limitation_type TEXT NOT NULL CHECK (
        limitation_type IN ('MISSING_CONTEXT', 'SOURCE_QUALITY', 'CONFLICT', 'GENERALIZABILITY',
                            'SEQUENCE_BOUNDARY', 'MEASUREMENT', 'LICENSE', 'OTHER')
    ),
    limitation_text TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('INFO', 'CAUTION', 'BLOCKING')),
    resolution_status TEXT NOT NULL CHECK (resolution_status IN ('OPEN', 'RESOLVED', 'ACCEPTED', 'NOT_RESOLVABLE')),
    FOREIGN KEY (limitation_key) REFERENCES kb_entity(entity_key)
) STRICT;

CREATE TABLE kb_claim_limitation (
    evidence_claim_key TEXT NOT NULL,
    limitation_key TEXT NOT NULL,
    PRIMARY KEY (evidence_claim_key, limitation_key),
    FOREIGN KEY (evidence_claim_key) REFERENCES kb_evidence_claim(evidence_claim_key),
    FOREIGN KEY (limitation_key) REFERENCES kb_limitation(limitation_key)
) STRICT;

CREATE TABLE kb_claim_conflict (
    conflict_key TEXT NOT NULL CHECK (conflict_key GLOB 'kbc:*'),
    evidence_claim_key TEXT NOT NULL,
    conflict_role TEXT NOT NULL CHECK (conflict_role IN ('CLAIM_A', 'CLAIM_B', 'ADDITIONAL')),
    conflict_type TEXT NOT NULL CHECK (
        conflict_type IN ('DIRECT_CONTRADICTION', 'CONTEXT_MISMATCH', 'MEASUREMENT_DISAGREEMENT',
                          'SOURCE_VERSION_MISMATCH', 'DUPLICATE_INTERPRETATION')
    ),
    resolution_status TEXT NOT NULL CHECK (resolution_status IN ('OPEN', 'HUMAN_RESOLVED', 'UNRESOLVED')),
    resolution_note TEXT NOT NULL,
    PRIMARY KEY (conflict_key, evidence_claim_key),
    FOREIGN KEY (evidence_claim_key) REFERENCES kb_evidence_claim(evidence_claim_key)
) STRICT;

CREATE TABLE kb_review_event (
    review_event_key TEXT PRIMARY KEY CHECK (review_event_key GLOB 'kbr:*'),
    entity_key TEXT NOT NULL,
    prior_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('HUMAN', 'AI', 'IMPORT')),
    reason TEXT NOT NULL,
    occurred_at_utc TEXT NOT NULL,
    FOREIGN KEY (entity_key) REFERENCES kb_entity(entity_key),
    CHECK (
        new_status NOT IN ('HUMAN_APPROVED', 'RUNTIME_ELIGIBLE', 'REGISTRY_ELIGIBLE')
        OR actor_type = 'HUMAN'
    )
) STRICT;

CREATE VIEW kb_runtime_claim_v0 AS
SELECT c.*
FROM kb_evidence_claim AS c
JOIN kb_entity AS e ON e.entity_key = c.evidence_claim_key
JOIN kb_evidence_level AS level ON level.evidence_level_key = c.evidence_level_key
WHERE c.fact_class = 'FACT'
  AND c.review_status = 'HUMAN_APPROVED'
  AND c.runtime_eligible = 1
  AND level.permits_runtime_use = 1
  AND e.lifecycle_status = 'ACTIVE'
  AND NOT EXISTS (
      SELECT 1
      FROM kb_claim_limitation AS link
      JOIN kb_limitation AS limitation ON limitation.limitation_key = link.limitation_key
      WHERE link.evidence_claim_key = c.evidence_claim_key
        AND limitation.severity = 'BLOCKING'
        AND limitation.resolution_status = 'OPEN'
  )
  AND NOT EXISTS (
      SELECT 1
      FROM kb_claim_conflict AS conflict
      WHERE conflict.evidence_claim_key = c.evidence_claim_key
        AND conflict.conflict_type = 'DIRECT_CONTRADICTION'
        AND conflict.resolution_status IN ('OPEN', 'UNRESOLVED')
  );

CREATE VIEW kb_registry_candidate_v0 AS
SELECT * FROM kb_runtime_claim_v0 WHERE registry_eligible = 1;

CREATE TRIGGER kb_source_reference_immutable_update
BEFORE UPDATE ON kb_source_reference
BEGIN
    SELECT RAISE(ABORT, 'source_reference identity is immutable; create a new source_reference_key');
END;

CREATE TRIGGER kb_source_reference_immutable_delete
BEFORE DELETE ON kb_source_reference
BEGIN
    SELECT RAISE(ABORT, 'source_reference rows cannot be deleted; retire the entity');
END;

CREATE TRIGGER kb_entity_revision_append_only_update
BEFORE UPDATE ON kb_entity_revision
BEGIN
    SELECT RAISE(ABORT, 'entity revisions are append-only');
END;

CREATE TRIGGER kb_entity_revision_append_only_delete
BEFORE DELETE ON kb_entity_revision
BEGIN
    SELECT RAISE(ABORT, 'entity revisions cannot be deleted');
END;

CREATE TRIGGER kb_review_event_append_only_update
BEFORE UPDATE ON kb_review_event
BEGIN
    SELECT RAISE(ABORT, 'review events are append-only');
END;

CREATE TRIGGER kb_review_event_append_only_delete
BEFORE DELETE ON kb_review_event
BEGIN
    SELECT RAISE(ABORT, 'review events cannot be deleted');
END;

CREATE TRIGGER kb_entity_no_hard_delete
BEFORE DELETE ON kb_entity
BEGIN
    SELECT RAISE(ABORT, 'entities cannot be hard deleted; use lifecycle_status');
END;
