"""Located citation evidence and recorded judgments, never automatic verification.

Preparation is free and may honestly remain insufficient. Existing independent
review roles supply judgments; no provider, downloader or second review loop is
introduced here. Human spot checks measure agreement, not scientific truth.
"""
from __future__ import annotations

import math
from pathlib import Path

from scripts import citation_audit, literature_workbench as wb
from scripts.research_artifacts import path_in, read, sha

OUTCOMES = {"supports", "contradicts", "insufficient"}


def manuscript_usages(project: Path, paper_id: str) -> list[dict]:
    from scripts.ref_verify_adapter import canonical_manuscript
    manuscript = canonical_manuscript(path_in(project, "papers/" + paper_id, exists=False))
    rows = citation_audit.citation_usages(manuscript)
    for row in rows:
        row["source"]["path"] = (manuscript.parent / row["source"]["path"]).relative_to(project).as_posix()
        row["usage_id"] = wb._digest({k: row[k] for k in ("citation_key", "source", "context")})[:24]
    return rows


def prepare(project: Path, spec: dict) -> dict:
    from scripts.ref_verify_adapter import canonical_manuscript
    from scripts.literature_source_tasks import _anchors, _full_text_available, _library
    from scripts.source_scope import _registered_basis
    if not isinstance(spec, dict) or set(spec) - {"schema_version", "id", "paper_id", "claims", "sample_labels"} or spec.get("schema_version") != "1.0":
        raise ValueError("unsupported claim-evidence request")
    identifier = wb._id(spec.get("id"))
    owner = spec.get("paper_id")
    import re
    if not isinstance(owner, str) or not re.fullmatch(r"P[0-9]{2}", owner):
        raise ValueError("claim evidence needs its actual manuscript paper")
    manuscript = canonical_manuscript(path_in(project, "papers/" + owner, exists=False))
    bibliography = path_in(project, f"papers/{owner}/manuscript/references.bib")
    entries = citation_audit.parse_bibtex(bibliography.read_text(encoding="utf-8"))
    if len({e["key"] for e in entries}) != len(entries):
        raise ValueError("duplicate citation keys")
    entries = {e["key"]: e for e in entries}
    usages = manuscript_usages(project, owner)
    papers = _library(project)[0] if (project / wb.CONFIG).is_file() else {}
    incoming = spec.get("claims")
    if not isinstance(incoming, list) or not 1 <= len(incoming) <= 500:
        raise ValueError("claim evidence needs 1..500 actual citation claims")
    claims, seen, scientific_claims = [], set(), set()
    for claim in incoming:
        if not isinstance(claim, dict) or set(claim) - {"claim_id", "claim", "citation_key", "library_id", "evidence"}:
            raise ValueError("unsupported citation claim fields")
        key = wb._id(claim.get("claim_id"))
        if key in seen:
            raise ValueError("duplicate citation claim")
        seen.add(key)
        statement = wb._text(claim.get("claim"), "actual manuscript claim")
        cite = claim.get("citation_key")
        if (statement, cite) in scientific_claims:
            raise ValueError("renamed duplicate claims cannot inflate the sampling population")
        scientific_claims.add((statement, cite))
        local = [row for row in usages if row["citation_key"] == cite and row["claim_text"] ==
            citation_audit.citation_prose(statement, tex=manuscript.suffix == ".tex")]
        if not local or cite not in entries:
            raise ValueError("claim text and citation key must identify the same complete current manuscript citation scope")
        doi = citation_audit.normalize_doi(entries[cite]["fields"].get("doi", ""))
        url = entries[cite]["fields"].get("url", "").strip()
        if doi and not re.fullmatch(r"10\.\d{4,9}/\S+", doi, re.I):
            raise ValueError("citation claim DOI is invalid")
        if not doi and not url.startswith("https://"):
            raise ValueError("citation claim needs its registered DOI or original HTTPS source URL")
        identity_url = "https://doi.org/" + doi if doi else url
        paper = papers.get(claim.get("library_id"))
        anchors = _anchors(project, paper, claim.get("evidence", [])) if paper else []
        missing, basis = [], None
        if not paper:
            if claim.get("evidence"):
                raise ValueError("unregistered original source cannot supply evidence")
            missing.append("Locate and lawfully acquire the cited work's original open-access full text.")
        else:
            if ((doi and citation_audit.normalize_doi(paper.get("url", "")) != doi)
                    or (not doi and paper.get("url", "").rstrip("/") != url.rstrip("/"))):
                raise ValueError("registered source DOI/URL differs from the cited work")
            from scripts.output_provenance import current_origin
            registration = path_in(project, "literature/metadata/" + paper["id"] + ".json", exists=False)
            config_origin = current_origin(project, path_in(project, wb.CONFIG))
            if paper.get("source_scope") != "full_text":
                missing.append("The registered source does not supply the original full text.")
            elif registration.exists() or config_origin.get("model") == "scripts/literature_registration.py":
                # A present controlled registration is a claim of authority: a
                # stale/deleted acquisition receipt cannot become mere absence.
                primary, basis = _registered_basis(project, paper["id"])
                if primary != paper["source"]:
                    raise ValueError("registered full-text source differs from the evidence library")
                if not _full_text_available(project, paper):
                    missing.append("Complete original full-text scope is unavailable.")
                grant = read(path_in(project, basis["manifest_path"])).get("license", {})
                license_url = grant.get("url", "")
                if (grant.get("research_use_allowed") is not True or not isinstance(license_url, str)
                        or not license_url.startswith(("https://creativecommons.org/licenses/", "https://creativecommons.org/publicdomain/"))):
                    missing.append("This OA-only checker needs the recorded public license grant; other full text stays insufficient.")
            else:
                missing.append("Full-text rights and controlled acquisition still need source registration evidence.")
        if not anchors:
            missing.append("Locate the relevant original paragraph/page, including contrary context.")
        claims.append({"claim_id": key, "claim": statement, "citation_key": cite, "doi": doi, "source_identity_url": identity_url,
            "manuscript_usages": local,
            "library_id": claim.get("library_id"), "evidence": anchors, "source_basis": basis,
            "source": paper["source"] if paper else None, "reader": paper.get("reader") if paper else None,
            "full_text_ready": not missing, "missing_evidence": missing, "outcome": "insufficient"})
    fingerprint = wb._digest({"claims": [{**{k: row[k] for k in ("claim_id", "claim", "citation_key", "doi", "source", "reader", "evidence", "source_basis", "manuscript_usages")},
        **({"source_identity_url": row["source_identity_url"]} if not row["doi"] else {})} for row in claims], "citation_usages": usages})
    sample = sorted(claims, key=lambda row: wb._digest([fingerprint, row["claim_id"]]))[:math.ceil(.15 * len(claims))]
    return {"schema_version": "1.0", "operation": "claim_evidence", "id": identifier, "paper_id": owner,
        "manuscript_sha256": citation_audit.manuscript_digest(manuscript), "bibliography_sha256": sha(bibliography),
        "claims": claims, "citation_usages": usages,
        "uncovered_usages": [row for row in usages if row["usage_id"] not in
            {use["usage_id"] for claim in claims for use in claim["manuscript_usages"]}],
        "claim_fingerprint": fingerprint, "sample_claim_ids": [r["claim_id"] for r in sample],
        "sample_fraction": .15, "semantic_support_verified": False, "scientific_completion_verified": False,
        "model_call_made": False, "role_contract": "Return claim_evidence:[{claim_id,outcome:supports|contradicts|insufficient,rationale,evidence:[original anchors],missing_evidence:[text]}]. Assess the entire located manuscript citation scope, including all assertions and contrary context. Preserve uncovered uses as missing evidence. Insufficient is valid; a quote match never proves support."}


def assess(project: Path, packet: dict, responses: list[dict], labels: dict | None = None) -> dict:
    """Consume current protected observations/panel responses after their checks."""
    from scripts.literature_source_tasks import _anchors, _library
    papers = _library(project)[0] if (project / wb.CONFIG).is_file() else {}
    claims = {r["claim_id"]: {**r, "judgments": []} for r in packet["claims"]}
    for response in responses:
        receipt = response["receipt"]
        seen = set()
        for row in response["response"].get("claim_evidence", []):
            key = row.get("claim_id")
            if key not in claims or key in seen or row.get("outcome") not in OUTCOMES:
                raise ValueError("independent claim judgment is outside its current packet")
            seen.add(key)
            wb._text(row.get("rationale"), "source judgment rationale")
            missing = row.get("missing_evidence", [])
            if not isinstance(missing, list) or any(not isinstance(v, str) or not v.strip() for v in missing):
                raise ValueError("missing evidence must remain explicit")
            claim = claims[key]
            evidence = _anchors(project, papers[claim["library_id"]], row.get("evidence", [])) if claim["library_id"] in papers else []
            if row["outcome"] != "insufficient" and (not claim["full_text_ready"] or not evidence):
                raise ValueError("support/contradiction requires lawful original full text and located evidence")
            if row["outcome"] == "insufficient" and not missing:
                raise ValueError("insufficient judgment needs its actual evidence gap")
            claim["judgments"].append({**row, "evidence": evidence, "review": receipt["response"],
                "role": receipt["role"], "identity": receipt["identity"]})
    for claim in claims.values():
        outcomes = {r["outcome"] for r in claim["judgments"]}
        claim["outcome"] = next(iter(outcomes)) if len(outcomes) == 1 and claim["full_text_ready"] else "insufficient"
        claim["disagreement"] = len(outcomes) > 1
        claim["assessment_status"] = "recorded_model_judgment" if outcomes else "awaiting_independent_source_review"
    sample = packet["sample_claim_ids"]
    checked, agreements = [], 0
    if labels is not None:
        from scripts.output_provenance import current_origin
        target = path_in(project, labels["path"])
        origin = current_origin(project, target)
        if sha(target) != labels.get("sha256") or origin.get("status") != "tracked" or origin.get("provider") != "human-attestation":
            raise ValueError("spot-check labels need current actual human-review provenance")
        annotation = read(target)
        if annotation.get("claim_fingerprint") != packet["claim_fingerprint"]:
            raise ValueError("spot-check labels belong to different claim/source versions")
        for row in annotation.get("labels", []):
            key = row.get("claim_id")
            if key not in sample or key in checked or row.get("outcome") not in OUTCOMES:
                raise ValueError("spot-check labels must cover distinct sampled claims")
            wb._text(row.get("rationale"), "spot-check rationale")
            checked.append(key)
            agreements += int(bool(claims[key]["judgments"]) and claims[key]["outcome"] == row["outcome"])
    complete = set(checked) == set(sample)
    covered = not packet["uncovered_usages"]
    agreement = agreements / len(sample) if covered and complete and all(claims[k]["judgments"] for k in sample) else None
    return {**packet, "claims": list(claims.values()), "spot_check": {"sample_claim_ids": sample,
        "reviewed_claim_ids": checked, "label_source": labels, "coverage_complete": covered,
        "status": "awaiting_complete_citation_coverage" if not covered else "recorded_human_comparison" if complete else "awaiting_real_labels",
        "agreement": agreement, "target_agreement": .85, "target_met": agreement >= .85 if agreement is not None else None,
        "scientific_validity_verified": False}}


def build(project: Path, spec: dict) -> dict:
    packet = prepare(project, spec)
    from scripts.literature_source_tasks import judgment_responses
    labels = spec.get("sample_labels")
    if isinstance(labels, str):
        target = path_in(project, labels, exists=False)
        labels = {"path": labels, "sha256": sha(target)} if target.is_file() else None
    return assess(project, packet, judgment_responses(project, spec["paper_id"]), labels)
