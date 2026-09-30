from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.plant_expression_candidate_ingestion.config import (
    EVIDENCE_STATUS_VALUES,
    PROVENANCE_STATUS_VALUES,
    RECORD_TYPES,
    REVIEW_STATUS_VALUES,
)
from services.plant_expression_candidate_ingestion.registry import QueryDefinition, SourceDefinition
from services.plant_expression_candidate_ingestion.utils import clean_text, content_hash


class NormalizationError(ValueError):
    """Raised for malformed source records that should be rejected."""


@dataclass
class NormalizedRecord:
    canonical_record_id: str
    record_type: str
    primary_name: str
    source_id: str
    source_record_id: str
    content_hash: str
    review_status: str = "needs_manual_review"
    provenance_status: str = "candidate"
    evidence_status: str = "metadata_candidate"
    aliases: list[str] = field(default_factory=list)
    identifiers: list[dict[str, str]] = field(default_factory=list)
    links: list[dict[str, str]] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    abstract_or_summary: str = ""
    pmid: str = ""
    pmcid: str = ""
    doi: str = ""
    accession: str = ""
    taxon_id: str = ""
    organism_name: str = ""
    publication_year: str = ""
    journal_or_repository: str = ""
    component_type_candidate: str = ""
    expression_context_candidate: str = ""
    assembly_standard_candidate: str = ""
    external_url: str = ""
    license_note: str = ""
    limitations: str = ""
    inference_records: list[dict[str, str]] = field(default_factory=list)

    def validate(self) -> None:
        if self.record_type not in RECORD_TYPES:
            raise NormalizationError(f"Unsupported record_type: {self.record_type}")
        if self.review_status not in REVIEW_STATUS_VALUES:
            raise NormalizationError(f"Unsupported review_status: {self.review_status}")
        if self.provenance_status not in PROVENANCE_STATUS_VALUES:
            raise NormalizationError(f"Unsupported provenance_status: {self.provenance_status}")
        if self.evidence_status not in EVIDENCE_STATUS_VALUES:
            raise NormalizationError(f"Unsupported evidence_status: {self.evidence_status}")
        if not self.source_id or not self.source_record_id:
            raise NormalizationError("Normalized record is missing source identity.")
        if not self.primary_name:
            raise NormalizationError("Normalized record is missing a primary name.")
        forbidden_statuses = {"recommended", "best", "validated", "accepted", "experiment_ready", "wet_lab_ready"}
        if self.review_status in forbidden_statuses or self.evidence_status in forbidden_statuses:
            raise NormalizationError("Unsafe automatic review or evidence status.")


def normalize_records(
    *,
    source: SourceDefinition,
    query: QueryDefinition,
    records: list[dict[str, Any]],
) -> tuple[list[NormalizedRecord], list[dict[str, Any]]]:
    normalized: list[NormalizedRecord] = []
    rejected: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        try:
            if source.adapter == "europe_pmc":
                item = normalize_europe_pmc_record(source=source, query=query, record=record)
            elif source.adapter == "uniprot":
                item = normalize_uniprot_record(source=source, query=query, record=record)
            else:
                raise NormalizationError(f"Unsupported source adapter: {source.adapter}")
            item.validate()
            normalized.append(item)
        except Exception as exc:
            rejected.append({"index": index, "reason": str(exc), "source_record_hint": clean_text(record.get("id"))})
    return normalized, rejected


def normalize_europe_pmc_record(
    *,
    source: SourceDefinition,
    query: QueryDefinition,
    record: dict[str, Any],
) -> NormalizedRecord:
    source_record_id = clean_text(record.get("id")) or clean_text(record.get("pmid")) or clean_text(record.get("pmcid"))
    title = clean_text(record.get("title"))
    if not source_record_id or not title:
        raise NormalizationError("Europe PMC record requires id and title.")
    pmid = clean_text(record.get("pmid"))
    pmcid = clean_text(record.get("pmcid"))
    doi = _normalize_doi(record.get("doi"))
    year = clean_text(record.get("pubYear") or record.get("journalInfo", {}).get("year"))
    journal = clean_text(record.get("journalTitle") or record.get("journalInfo", {}).get("journal", {}).get("title"))
    if _first_url(record):
        external_url = _first_url(record)
    elif pmid:
        external_url = f"https://europepmc.org/article/MED/{pmid}"
    else:
        external_url = f"https://europepmc.org/article/{source_record_id}"
    identifiers = [{"identifier_type": f"{source.source_id}:source_record_id", "identifier_value": source_record_id}]
    if pmid:
        identifiers.append({"identifier_type": "PMID", "identifier_value": pmid})
    if pmcid:
        identifiers.append({"identifier_type": "PMCID", "identifier_value": pmcid})
    if doi:
        identifiers.append({"identifier_type": "DOI", "identifier_value": doi})
    stable_key = doi or pmid or pmcid or f"{source.source_id}:{source_record_id}"
    inferred = _infer_candidate_fields(query=query, text=f"{title} {record.get('abstractText', '')}")
    return NormalizedRecord(
        canonical_record_id=_canonical_id("publication", stable_key),
        record_type="publication",
        primary_name=title,
        source_id=source.source_id,
        source_record_id=source_record_id,
        content_hash=content_hash(record),
        identifiers=identifiers,
        links=[{"link_type": "source", "url": external_url}] if external_url else [],
        raw_metadata=record,
        description=clean_text(record.get("authorString")),
        abstract_or_summary=clean_text(record.get("abstractText")),
        pmid=pmid,
        pmcid=pmcid,
        doi=doi,
        publication_year=year,
        journal_or_repository=journal or source.source_name,
        component_type_candidate=inferred["component_type_candidate"],
        expression_context_candidate=inferred["expression_context_candidate"],
        assembly_standard_candidate=inferred["assembly_standard_candidate"],
        external_url=external_url,
        license_note=source.license_note,
        limitations="Metadata candidate only; abstract retained when provided by the source API; manual source review required.",
        inference_records=inferred["inference_records"],
    )


def normalize_uniprot_record(
    *,
    source: SourceDefinition,
    query: QueryDefinition,
    record: dict[str, Any],
) -> NormalizedRecord:
    accession = clean_text(record.get("primaryAccession"))
    if not accession:
        raise NormalizationError("UniProt record requires primaryAccession.")
    protein_name = _uniprot_protein_name(record) or clean_text(record.get("uniProtkbId")) or accession
    organism = record.get("organism") if isinstance(record.get("organism"), dict) else {}
    taxon_id = clean_text(organism.get("taxonId"))
    organism_name = clean_text(organism.get("scientificName"))
    aliases = _uniprot_aliases(record)
    summary = _uniprot_summary(record)
    identifiers = [
        {"identifier_type": "UniProt accession", "identifier_value": accession},
        {"identifier_type": f"{source.source_id}:source_record_id", "identifier_value": accession},
    ]
    inferred = _infer_candidate_fields(query=query, text=f"{protein_name} {summary} {' '.join(aliases)}")
    return NormalizedRecord(
        canonical_record_id=_canonical_id("sequence_or_accession", accession),
        record_type="sequence_or_accession",
        primary_name=protein_name,
        source_id=source.source_id,
        source_record_id=accession,
        content_hash=content_hash(record),
        evidence_status="accession_metadata_candidate",
        aliases=aliases,
        identifiers=identifiers,
        links=[{"link_type": "source", "url": f"https://www.uniprot.org/uniprotkb/{accession}/entry"}],
        raw_metadata=record,
        description=summary,
        abstract_or_summary=summary,
        accession=accession,
        taxon_id=taxon_id,
        organism_name=organism_name,
        journal_or_repository=source.source_name,
        component_type_candidate=inferred["component_type_candidate"] or "CDS/protein identity metadata",
        expression_context_candidate=inferred["expression_context_candidate"],
        assembly_standard_candidate=inferred["assembly_standard_candidate"],
        external_url=f"https://www.uniprot.org/uniprotkb/{accession}/entry",
        license_note=source.license_note,
        limitations="Protein/accession metadata candidate only; no component suitability or biological outcome is inferred.",
        inference_records=inferred["inference_records"],
    )


def _canonical_id(record_type: str, stable_key: str) -> str:
    return f"{record_type}:{content_hash({'stable_key': stable_key})[:20]}"


def _normalize_doi(value: Any) -> str:
    doi = clean_text(value).removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    return doi.lower()


def _first_url(record: dict[str, Any]) -> str:
    full_text_url_list = record.get("fullTextUrlList", {}).get("fullTextUrl")
    if isinstance(full_text_url_list, list):
        for item in full_text_url_list:
            if isinstance(item, dict) and clean_text(item.get("url")):
                return clean_text(item.get("url"))
    return ""


def _uniprot_protein_name(record: dict[str, Any]) -> str:
    protein = record.get("proteinDescription")
    if not isinstance(protein, dict):
        return ""
    recommended = protein.get("recommendedName")
    if isinstance(recommended, dict):
        full = recommended.get("fullName")
        if isinstance(full, dict):
            return clean_text(full.get("value"))
    submission = protein.get("submissionNames")
    if isinstance(submission, list):
        for item in submission:
            if isinstance(item, dict) and isinstance(item.get("fullName"), dict):
                name = clean_text(item["fullName"].get("value"))
                if name:
                    return name
    return ""


def _uniprot_aliases(record: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    if clean_text(record.get("uniProtkbId")):
        aliases.append(clean_text(record.get("uniProtkbId")))
    for gene in record.get("genes") or []:
        if not isinstance(gene, dict):
            continue
        name = gene.get("geneName")
        if isinstance(name, dict) and clean_text(name.get("value")):
            aliases.append(clean_text(name.get("value")))
        for synonym in gene.get("synonyms") or []:
            if isinstance(synonym, dict) and clean_text(synonym.get("value")):
                aliases.append(clean_text(synonym.get("value")))
    return sorted(set(aliases))


def _uniprot_summary(record: dict[str, Any]) -> str:
    parts = []
    for comment in record.get("comments") or []:
        if not isinstance(comment, dict):
            continue
        if clean_text(comment.get("commentType")) == "SUBCELLULAR LOCATION":
            locations = []
            for loc in comment.get("subcellularLocations") or []:
                if isinstance(loc, dict):
                    location = loc.get("location")
                    if isinstance(location, dict) and clean_text(location.get("value")):
                        locations.append(clean_text(location.get("value")))
            if locations:
                parts.append("Subcellular location metadata: " + "; ".join(locations))
    keywords = [
        clean_text(item.get("name"))
        for item in record.get("keywords") or []
        if isinstance(item, dict) and clean_text(item.get("name"))
    ]
    if keywords:
        parts.append("Keywords: " + "; ".join(keywords[:12]))
    return " ".join(parts)


def _infer_candidate_fields(query: QueryDefinition, text: str) -> dict[str, Any]:
    domain = query.domain_label.casefold()
    lowered = text.casefold()
    component = ""
    assembly = ""
    context = ""
    if "promoter" in domain or "promoter" in lowered:
        component = "promoter/regulatory region metadata"
    elif "terminator" in domain or "terminator" in lowered:
        component = "terminator/3 prime regulatory region metadata"
    elif "utr" in domain or "5 prime" in domain:
        component = "5 prime regulatory region or UTR metadata"
    elif "signal" in domain or "targeting" in domain:
        component = "signal or targeting peptide metadata"
    elif "marker" in domain or "reporter" in domain:
        component = "marker or reporter metadata"
    elif "vector" in domain or "toolkit" in domain or "backbone" in domain:
        component = "vector or toolkit metadata"
    if "transient" in domain or "transient" in lowered:
        context = "transient-expression context"
    elif "stable" in domain or "stable" in lowered:
        context = "stable-expression context"
    if "moclo" in domain or "golden gate" in domain or "phytobrick" in domain or "sbol" in domain:
        assembly = query.domain_label
    inference_records = []
    for field, value in (
        ("component_type_candidate", component),
        ("expression_context_candidate", context),
        ("assembly_standard_candidate", assembly),
    ):
        if value:
            inference_records.append(
                {
                    "field_name": field,
                    "inferred_value": value,
                    "inference_method": "deterministic_keyword_mapping",
                    "source_field": "query.domain_label + source metadata text",
                    "mapping_rule_version": "r225.v1",
                    "confidence_category": "broad_candidate_category",
                }
            )
    return {
        "component_type_candidate": component,
        "expression_context_candidate": context,
        "assembly_standard_candidate": assembly,
        "inference_records": inference_records,
    }
