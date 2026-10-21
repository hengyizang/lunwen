"""Select real discovery candidates into the shared library; no screening approval."""
from __future__ import annotations
import hashlib
from pathlib import Path
from urllib.parse import urlsplit
from scripts.research_artifacts import path_in, read, record, sha, write


def register(project: Path, candidate_id: str, *, expected_leads_sha256: str,
             paper_id=None, acquisition_receipt=None, manifest=None, reader=None,
             config_path="program/literature-workbench.json") -> dict:
    from scripts import literature_intelligence as intelligence, literature_workbench as workbench
    from scripts.literaturectl import approved_pdf, require_cloud
    from scripts.output_provenance import current_origin
    require_cloud()
    project = Path(project).resolve()
    if config_path != "program/literature-workbench.json":
        raise ValueError("Registration uses the shared program/literature-workbench.json")
    leads_path = path_in(project, intelligence.OUTPUT)
    if sha(leads_path) != expected_leads_sha256:
        raise ValueError("Discovery selection requires the exact current topic-leads hash")
    origin = current_origin(project, leads_path)
    if origin.get("status") != "tracked" or origin.get("family") == "anthropic":
        raise ValueError("Discovery leads require current non-Claude executor provenance")
    leads = read(leads_path)
    if leads.get("kind") != "literature_discovery_intelligence":
        raise ValueError("Select only executed literature discovery leads")
    intelligence._scope(project, leads.get("doctoral_question"))
    candidate = next((row for row in leads.get("candidates", []) if row.get("canonical_id") == candidate_id), None)
    if candidate is None:
        raise ValueError("Candidate does not occur in the selected discovery report")
    for reference in candidate.get("source_refs", []):
        for name, digest in (("raw_response_path", "response_sha256"),
                             ("normalized_results_path", "normalized_results_sha256")):
            if sha(path_in(project, reference[name])) != reference[digest]:
                raise ValueError("Candidate source receipt is stale")
    if not candidate.get("source_refs"):
        raise ValueError("Candidate requires actual executed source receipts")
    identifier = paper_id or "paper-" + hashlib.sha256(candidate_id.encode()).hexdigest()[:16]
    workbench._id(identifier, "literature paper ID")
    metadata_path = path_in(project, "literature/metadata/" + identifier + ".json", exists=False)
    metadata = {"schema_version": "1.0", "source_scope": "metadata_only", "candidate": candidate,
                "discovery_sha256": expected_leads_sha256, "human_screening_approved": False,
                "full_text_reading_verified": False, "scientific_completion_verified": False}
    spec = {"id": identifier, "title": candidate["title"], "candidate_id": candidate_id,
            "topic_id": "thesis-" + hashlib.sha256(leads["doctoral_question"].encode()).hexdigest()[:16],
            "paper_ids": [], "source_scope": "metadata_only"}
    primary = candidate.get("primary_source_url")
    if isinstance(primary, str) and primary.startswith("https://"):
        spec["url"] = primary
    attachment = "metadata_only"
    if acquisition_receipt is not None:
        if not isinstance(acquisition_receipt, dict):
            raise ValueError("Acquisition needs an exact manifest path/hash binding")
        relative = acquisition_receipt.get("path", "")
        if not relative.startswith("evidence/literature/assets/") or sha(path_in(project, relative)) != acquisition_receipt.get("sha256"):
            raise ValueError("Acquisition manifest binding is stale or outside source receipts")
        receipt_path = path_in(project, relative)
        asset_origin = current_origin(project, receipt_path)
        if asset_origin.get("status") != "tracked" or asset_origin.get("family") == "anthropic":
            raise ValueError("Acquisition must have current executor provenance")
        acquired = read(receipt_path)
        metadata["acquisition_receipt"] = acquisition_receipt
        direct = acquired.get("source_url") == primary or acquired.get("original_input") == primary
        arxiv = acquired.get("arxiv_id")
        identity = intelligence.canonical_match(candidate, {"arxiv_id": arxiv, "title": acquired.get("title"),
            "authors": acquired.get("authors", []), "publication_year":
                int(acquired["publication_date"][:4]) if str(acquired.get("publication_date", ""))[:4].isdigit() else None})
        if not direct and not identity:
            attachment = "source_identity_unresolved_metadata_retained"
        elif not manifest:
            attachment = "full_text_rights_review_pending"
        elif not acquired.get("pdfs"):
            attachment = "no_acquired_pdf_metadata_retained"
        else:
            pdf = acquired["pdfs"][0]
            actual = approved_pdf(project, pdf["path"], manifest)
            if sha(actual) != pdf["sha256"]:
                raise ValueError("Acquired PDF no longer matches its receipt")
            spec.update(source={"path": pdf["path"], "sha256": pdf["sha256"]},
                        manifest=manifest, source_scope="full_text")
            if reader:
                files = workbench._Files(project)
                source = workbench.source_binding(project, spec["source"], manifest=manifest, files=files)
                workbench._reader(project, reader, source, files)
                spec["reader"] = reader
            attachment = "authorized_full_text_attached_semantics_pending"
    elif manifest or reader:
        raise ValueError("Full-text attachments need their acquisition receipt")
    write(metadata_path, metadata)
    record(project, [metadata_path], "scripts/literature_registration.py")
    spec.setdefault("source", {"path": metadata_path.relative_to(project).as_posix(), "sha256": sha(metadata_path)})
    config_file = path_in(project, config_path, exists=False)
    config = read(config_file) if config_file.is_file() else {"schema_version": "1.0", "papers": []}
    if config.get("doctoral_question") not in {None, leads["doctoral_question"]}:
        raise ValueError("Do not mix doctoral questions in a shared library")
    config["doctoral_question"] = leads["doctoral_question"]
    papers = config.setdefault("papers", [])
    previous = next((p for p in papers if p.get("id") == identifier), None)
    if previous:
        if previous.get("candidate_id") != candidate_id:
            raise ValueError("Library ID already belongs to another source")
        if previous.get("source") == spec["source"]:
            spec = {**previous, **spec}
        elif previous.get("card") or previous.get("reader"):
            raise ValueError("Preserve analyzed prior versions before rebinding a paper")
        papers[papers.index(previous)] = spec
    else:
        papers.append(spec)
    write(config_file, config)
    record(project, [config_file], "scripts/literature_registration.py")
    built = workbench.build(project)
    return {"paper_id": identifier, "candidate_id": candidate_id, "attachment_status": attachment,
            "library": built, "human_screening_approved": False, "paid_model_calls": 0}
