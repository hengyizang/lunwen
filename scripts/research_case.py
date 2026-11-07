"""One source-aware workbench for the paper's argument and local release materials.

Preparation is progressive: missing evidence stays visible, without another gate,
model call, experiment, publication action or acceptance score. Frozen contracts
remain the authority; an evolving case never edits them.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.research_artifacts import path_in, read, record, sha, write
from scripts.paper_execution import artifact_path, paper_scoped
from scripts.journal_dossier import FIT_FIELDS as VENUE_FIELDS

FIGURE_ROLES = {"main_result", "strongest_baseline", "negative_boundary"}
KINDS = {"case", "preprint", "rebuttal", "retarget", "reproduction"}


def _paper(paper_id):
    if not isinstance(paper_id, str) or not re.fullmatch(r"P[0-9]{2}", paper_id):
        raise ValueError("an exact paper ID is required")
    return f"papers/{paper_id}"


def _binding(project, source, *, located=False):
    if not isinstance(source, dict):
        raise ValueError("a current source binding is required")
    path = path_in(project, source.get("path", ""))
    if source.get("sha256") != sha(path):
        raise ValueError("source changed: " + source["path"])
    if located:
        from scripts.research_candidates import anchor_errors
        errors = anchor_errors(project, source)
        if errors:
            raise ValueError("; ".join(errors))
    return path


def _nonempty(value):
    return isinstance(value, str) and value.strip().casefold() not in {"", "unknown", "tbd", "todo"}


def _ids(value, allowed):
    return (isinstance(value, list) and bool(value) and all(isinstance(v, str) for v in value)
            and len(set(value)) == len(value) and set(value) <= allowed)


def competition(project, spec, *, today=None):
    """Count a retrieved, explicitly selected problem cohort, never the whole field.

    Submission dates and research-group identities are usually unavailable in
    bibliographic APIs. Publication/preprint windows and author-overlap components
    are reported as such; unknowns never become zero competition.
    """
    from scripts.literature_intelligence import _receipt_works, canonical_identity, deduplicate, _authors
    current = today or date.today()
    ledger = path_in(project, "evidence/literature-api-ledger.jsonl")
    receipts = {r["receipt_id"]: r for r in (json.loads(line) for line in ledger.read_text().splitlines() if line.strip())}
    works, sources = [], []
    for receipt_id in spec.get("receipt_ids", []):
        if receipt_id not in receipts:
            raise ValueError("unknown literature receipt: " + str(receipt_id))
        rows, source = _receipt_works(project, receipts[receipt_id])
        works.extend(rows)
        sources.append(source)
    if not sources:
        raise ValueError("competition needs actual literature retrieval receipts")
    indexed = {canonical_identity(w): w for w in deduplicate(works)}
    selected = spec.get("same_problem_ids")
    if not _ids(selected, set(indexed)):
        raise ValueError("competition needs explicit same-problem IDs from the retrieved sources")
    closest = spec.get("closest_work_id")
    if closest not in selected:
        raise ValueError("closest_work_id must be part of the compared problem cohort")
    # Calendar-year windows, including leap-day handling.
    def anniversary(year):
        try:
            return current.replace(year=year)
        except ValueError:
            return date(year, 2, 28)
    recent_start, previous_start = anniversary(current.year - 1), anniversary(current.year - 2)
    recent, previous, unknown_dates, dates, groups, unknown_authors = [], [], [], {}, [], []
    for identifier in selected:
        work = indexed[identifier]
        try:
            published = date.fromisoformat(work.get("publication_date", ""))
            if published > current:
                raise ValueError("future date")
            dates[identifier] = published
            if published > recent_start:
                recent.append(identifier)
            elif published > previous_start:
                previous.append(identifier)
        except (ValueError, TypeError):
            unknown_dates.append(identifier)
        authors = _authors(work)
        if not authors:
            unknown_authors.append(identifier)
            continue
        touching = [g for g in groups if g & authors]
        groups = [g for g in groups if not g & authors]
        groups.append(set().union(authors, *touching))
    return {"as_of": current.isoformat(), "sources": sources, "same_problem_ids": selected,
            "recent_12_months": len(recent), "previous_12_months": len(previous),
            "growth_fraction": (len(recent) / len(previous) - 1) if previous and not unknown_dates else None,
            "closest_age_days": (current - dates[closest]).days if closest in dates else None,
            "author_overlap_components": len(groups) if not unknown_authors else None,
            "unknown_dates": unknown_dates, "unknown_authors": unknown_authors,
            "submission_growth": None, "actual_competing_groups": None,
            "interpretation": "Retrieved publication/preprint cohort only; relevance and author overlap require review. No automatic topic elimination.",
            "decision": spec.get("decision", "unknown"), "decision_reason": spec.get("decision_reason", "unknown")}


def _case_findings(project, case, contract, protocol):
    """Identify useful work, not a second administrative pass/fail checklist."""
    missing = []
    claims = set(contract.get("independence", {}).get("unique_claim_ids", []))
    tests = {t["test_id"] for t in protocol.get("critical_tests", [])}
    contribution = case.get("contribution", {})
    for name in ("headline_claim", "counterclaim"):
        if not _nonempty(contribution.get(name)):
            missing.append("contribution." + name)
    if _nonempty(contribution.get("headline_claim")) and str(contribution.get("counterclaim", "")).strip().casefold() == contribution["headline_claim"].strip().casefold():
        missing.append("counterclaim must state a distinguishable alternative to the headline")
    if not _ids(contribution.get("claim_ids"), claims):
        missing.append("contribution.claim_ids must use this paper's contracted claims")
    if not _ids(contribution.get("test_ids"), tests):
        missing.append("contribution.test_ids must name actual discriminating tests")
    readers = contribution.get("reader_benefits", [])
    if (len(readers) != 3 or any(not isinstance(r, dict) or not _nonempty(r.get("reader"))
                               or not _nonempty(r.get("benefit")) for r in readers)
            or len({r.get("reader") for r in readers if isinstance(r, dict)}) != 3):
        missing.append("contribution.reader_benefits needs three distinct readers and their benefit")
    premortem = case.get("pre_mortem", [])
    if not premortem:
        missing.append("pre_mortem: strongest rejection argument before G3 freezing")
    for row in premortem:
        if not all(_nonempty(row.get(k)) for k in ("id", "rejection_reason", "response", "decision")) or not _ids(row.get("test_ids"), tests):
            missing.append("pre_mortem needs a rejection reason and response linked to existing test IDs")
    figures = case.get("figure_first", [])
    comparisons = {c["comparison_id"]: c for c in protocol.get("comparisons", [])}
    if {f.get("role") for f in figures} != FIGURE_ROLES:
        missing.append("figure_first needs main_result, strongest_baseline and negative_boundary plans")
    for figure in figures:
        if not _ids(figure.get("claim_ids"), claims) or not _ids(figure.get("comparison_ids"), set(comparisons)):
            missing.append("figure_first requires current claim/comparison IDs; planned figures contain no invented numbers")
        else:
            selected = [comparisons[c] for c in figure["comparison_ids"]]
            if figure.get("role") == "negative_boundary" and not any(c.get("role") in {"negative_control", "robustness", "external_validation"} for c in selected):
                missing.append("negative_boundary needs a registered adverse/control or boundary comparison")
        if figure.get("phase", "planned") != "planned" and not figure.get("source"):
            missing.append("observed figure needs its actual figure_story/publication_figures source")
    variants = case.get("variants", [])
    identifiers = [row.get("id") for row in variants]
    if len(set(identifiers)) != len(identifiers) or case.get("selected_variant") not in identifiers:
        missing.append("select a unique retained title/abstract variant")
    for row in variants:
        if not all(_nonempty(row.get(k)) for k in ("id", "title", "abstract", "reason")) or not row.get("keywords") or not _ids(row.get("claim_ids"), claims):
            missing.append("each title/abstract variant needs keywords, reason and contracted claim IDs")
    for row in case.get("positioning", []):
        if not all(_nonempty(row.get(k)) for k in ("work_id", "shared", "difference", "prediction")) or not row.get("source"):
            missing.append("related-work positioning needs located shared elements, differences and discriminating predictions")
    venue = case.get("venue_fit", {})
    for field in VENUE_FIELDS:
        item = venue.get(field, {})
        if not _nonempty(item.get("statement")) or not item.get("source"):
            missing.append("venue_fit." + field + " remains unknown without current official evidence")
    # Reuse the exact source-location verifier wherever the case uses evidence.
    def anchors(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"source", "rights_source"} and isinstance(item, dict):
                    try:
                        _binding(project, item, located=True)
                    except (ValueError, OSError) as exc:
                        missing.append(str(exc))
                else:
                    anchors(item)
        elif isinstance(value, list):
            for item in value:
                anchors(item)
    anchors(case)
    return list(dict.fromkeys(missing))


@paper_scoped
def build_packet(project: Path, paper_id: str, *, today=None, sections=None):
    prefix = _paper(paper_id)
    sources, absent = [], []
    def load(relative):
        target = path_in(project, relative, exists=False)
        if not target.is_file():
            absent.append(relative)
            return {}
        sources.append({"path": relative, "sha256": sha(target)})
        return read(target)
    contract = load(prefix + "/paper-contract.json")
    case = load(prefix + "/research-case.json")
    if case and (case.get("schema_version") != "1.0" or case.get("paper_id") != paper_id):
        raise ValueError("research case identity differs from the selected paper")
    if case:
        import jsonschema
        try:
            jsonschema.validate(case, read(Path(__file__).resolve().parents[1] / "schemas/research-case.schema.json"))
        except jsonschema.ValidationError as exc:
            raise ValueError("invalid progressive research case: " + exc.message) from exc
    protocol = load(prefix + "/experiment-evidence-plan.json")
    mapping = load("program/paper-map.json")
    matrix = artifact_path(project, "claims/claim-evidence.csv", paper_id)
    claims = []
    if matrix.is_file():
        sources.append({"path": matrix.relative_to(project).as_posix(), "sha256": sha(matrix)})
        claims = [row for row in csv.DictReader(io.StringIO(matrix.read_text())) if row.get("paper_id") == paper_id]
    findings = absent + _case_findings(project, case, contract, protocol)
    crowding = {"status": "unknown", "reason": "No compared retrieved cohort supplied."}
    if case.get("competition"):
        try:
            crowding = competition(project, case["competition"], today=today)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            findings.append("competition: " + str(exc))
    # A table with every paper, including papers not executed yet, is a useful
    # synthesis input. It never turns a proposed common mechanism into a result.
    cumulative = []
    for paper in mapping.get("papers", []):
        pid = paper["paper_id"]
        source = artifact_path(project, "claims/claim-evidence.csv", pid)
        rows = [r for r in csv.DictReader(io.StringIO(source.read_text())) if r.get("paper_id") == pid] if source.is_file() else []
        if source.is_file():
            sources.append({"path": source.relative_to(project).as_posix(), "sha256": sha(source)})
        cumulative.append({"paper_id": pid, "contribution": paper.get("distinct_contribution"),
                           "claim_ids": paper.get("unique_claim_ids", []), "result_rows": rows,
                           "evidence_status": "recorded_requires_review" if rows else "not_executed_or_unreported"})
    result = {"schema_version": "1.0", "paper_id": paper_id,
            "status": "preparation" if findings else "ready_for_review", "missing_evidence": findings,
            "sources": list({s["path"]: s for s in sources}.values()), "case": case,
            "contribution": case.get("contribution", {}), "pre_mortem": case.get("pre_mortem", []),
            "critical_tests": protocol.get("critical_tests", []), "competition": crowding,
            "figure_first": case.get("figure_first", []), "claim_rows": claims,
            "thesis_synthesis": mapping.get("thesis_synthesis", {}), "cumulative_results": cumulative,
            "variants": case.get("variants", []), "positioning": case.get("positioning", []),
            "venue_fit": case.get("venue_fit", {}), "cover_letter": case.get("cover_letter", {}),
            "rebuttal": case.get("rebuttal", []),
            "limits": {"scientific_validity_verified": False, "acceptance_probability": None,
                       "paid_model_calls": 0, "execution_authorized": False, "external_publication": False}}
    if sections is not None:
        allowed = set(result) - {"case", "schema_version", "paper_id", "status", "sources", "missing_evidence", "limits"}
        if not isinstance(sections, list) or not all(isinstance(s, str) and s in allowed for s in sections):
            raise ValueError("packet sections must name existing scientific sections")
        result = {k: v for k, v in result.items() if k in set(sections) | {"schema_version", "paper_id", "status", "sources", "missing_evidence", "limits"}}
    return result


def _table(rows):
    handle = io.StringIO(newline="")
    fields = list(dict.fromkeys(key for row in rows for key in row))
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                         for key, value in row.items()})
    return handle.getvalue().encode()


def _venue_sources(project, case, venue_id):
    """Fit is separate from ranking and never guesses publisher policy."""
    fit = case.get("venue_fit", {})
    if not _nonempty(venue_id) or fit.get("venue_id") != venue_id:
        raise ValueError("target needs its own source-bound venue_fit")
    ledger = read(path_in(project, "evidence/journal-sources/index.json"))["sources"]
    from urllib.parse import urlsplit
    dossiers = read(path_in(project, "program/journal-dossiers.json")).get("journals", [])
    official = next((set(r.get("official_domains", [])) for r in dossiers if r.get("venue_id") == venue_id), set())
    if not official:
        raise ValueError("target venue official source domains remain unknown")
    for field in VENUE_FIELDS:
        item = fit.get(field, {})
        source = item.get("source", {})
        path = _binding(project, source, located=True)
        receipt = ledger.get(item.get("url"), {})
        url = urlsplit(item.get("url", ""))
        if url.scheme != "https" or url.hostname not in official or url.username or url.password or not _nonempty(item.get("statement")) or receipt.get("status") != "retrieved" or receipt.get("path") != source.get("path") or receipt.get("sha256") != sha(path):
            raise ValueError("venue fit needs actual official retrieval evidence: " + field)
        retrieved = datetime.fromisoformat(receipt.get("retrieved_at", "").replace("Z", "+00:00"))
        final = urlsplit(receipt.get("final_url", ""))
        if (retrieved.tzinfo is None or retrieved > datetime.now(timezone.utc) or receipt.get("http_status") != 200
                or final.scheme != "https" or final.hostname not in official or final.username or final.password):
            raise ValueError("venue fit needs a dated successful official retrieval")
        if sha(path_in(project, receipt["raw_path"])) != receipt.get("raw_sha256"):
            raise ValueError("changed official venue response")
    return fit


def _registered_identifier(project, identifier, variants):
    """A manuscript mention alone cannot establish an externally assigned DOI."""
    _binding(project, identifier.get("source"), located=True)
    value = identifier.get("value", "")
    from scripts.literature_intelligence import _receipt_works, canonical_identity
    identity = canonical_identity({"doi": value}) if isinstance(value, str) else ""
    if identifier.get("status") != "registered" or not identity.startswith("doi:10.") or value not in identifier["source"]["excerpt"]:
        raise ValueError("a persistent identifier needs its actual registration evidence")
    ledger = path_in(project, "evidence/literature-api-ledger.jsonl")
    receipts = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    receipt = next((r for r in receipts if r.get("receipt_id") == identifier.get("receipt_id")), None)
    if not receipt or identifier["source"]["path"] not in {receipt.get("normalized_results_path"), receipt.get("raw_response_path")}:
        raise ValueError("registered DOI needs its actual bibliographic retrieval receipt")
    works, _ = _receipt_works(project, receipt)
    normalize = lambda title: " ".join(re.findall(r"\w+", str(title).casefold()))
    titles = {normalize(row.get("title")) for row in variants}
    if not any(canonical_identity(work) == identity and normalize(work.get("title")) in titles for work in works):
        raise ValueError("registered DOI does not identify a retained manuscript title in the retrieved metadata")


@paper_scoped
def export(project: Path, paper_id: str, kind: str):
    """Prepare local versioned materials. No submission, upload or new execution."""
    if kind not in KINDS:
        raise ValueError("unknown research-case export kind")
    packet = build_packet(project, paper_id)
    case, files, origins = packet["case"], {}, []
    def put(name, value):
        files[name] = value if isinstance(value, bytes) else value.encode("utf-8")
    def copy(binding, *, executed=False):
        path = _binding(project, binding)
        relative = path.relative_to(project).as_posix()
        from scripts.submission_package import safe_file, ResearchCtlError
        try:
            safe_file(path, project)
        except ResearchCtlError as exc:
            raise ValueError(str(exc)) from exc
        owners = re.findall(r"(?:^|/)papers/(P[0-9]{2})(?:/|$)", relative)
        if any(owner != paper_id for owner in owners):
            raise ValueError("release source belongs to another paper: " + relative)
        if path.stat().st_size > 20_000_000 or sum(map(len, files.values())) + path.stat().st_size > 32_000_000:
            raise ValueError("minimal release excludes large artifacts; use a rights-checked data reference")
        if not executed:
            origins.append(path)
        put("sources/" + relative, path.read_bytes())
        return "sources/" + relative
    put("research-case.json", json.dumps(packet, ensure_ascii=False, indent=2) + "\n")
    put("thesis-results.csv", _table(packet["cumulative_results"]))
    if packet["positioning"]:
        put("related-work.csv", _table(packet["positioning"]))
    if kind != "case":
        # Existing evidence engine replays frozen inputs, runner receipts, all
        # comparisons and adverse results. No model-authored result authority.
        from scripts.experiment_evidence import build_report
        report = build_report(project, paper_id)
        if report.get("status") != "complete" or report.get("errors"):
            raise ValueError("release needs actual complete executor evidence: " + "; ".join(report.get("errors", [])))
        put("results.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        put("results.csv", _table(report.get("comparisons", [])))
        registry_path = artifact_path(project, "experiments/registry.jsonl", paper_id)
        attempts = [json.loads(line) for line in registry_path.read_text().splitlines() if line.strip()]
        put("attempts.json", json.dumps([{k: row.get(k) for k in ("run_id", "attempt_id", "status", "exit_code", "estimated_cost_usd", "outputs")}
                                         for row in attempts if row.get("paper_id") == paper_id], indent=2) + "\n")
        for source in packet["sources"]:
            if source["path"].endswith("research-case.json"):
                origins.append(_binding(project, source))
    if kind in {"preprint", "retarget"}:
        versions = {row["id"]: row for row in case.get("variants", [])}
        variant = versions.get(case.get("selected_variant"))
        if not variant or not _nonempty(variant.get("title")) or not _nonempty(variant.get("abstract")):
            raise ValueError("select a retained title/abstract version before release preparation")
        put("title-abstract.md", variant["title"] + "\n\n" + variant["abstract"] + "\n\nKeywords: " + ", ".join(variant.get("keywords", [])) + "\n")
        spec = case.get(kind, {})
        sources = spec.get("manuscript_sources", [])
        if not sources:
            raise ValueError("local release needs current manuscript source bindings")
        for source in sources:
            if not source.get("path", "").startswith(_paper(paper_id) + "/manuscript/"):
                raise ValueError("release manuscript must belong to the selected paper")
            copy(source)
        identifier = spec.get("persistent_identifier", {"status": "unknown", "reason": "Not registered; preparation only."})
        if identifier.get("status") != "unknown":
            _registered_identifier(project, identifier, list(versions.values()))
        put("persistent-identifier.json", json.dumps(identifier, indent=2) + "\n")
        if kind == "retarget":
            fit = _venue_sources(project, case, spec.get("target_venue_id"))
            if not _nonempty(spec.get("previous_venue_id")) or not spec.get("previous_manuscript") or not spec.get("changes"):
                raise ValueError("retarget retains the previous venue, manuscript versions and explicit changes")
            for source in spec["previous_manuscript"]:
                relative = source.get("path", "")
                manuscript = _paper(paper_id) + "/manuscript/"
                retained = re.fullmatch(re.escape(_paper(paper_id)) + r"/release-preparation/(?:preprint|retarget)-[0-9a-f]{64}/sources/" + re.escape(manuscript) + r".+", relative)
                if not relative.startswith(manuscript) and not retained:
                    raise ValueError("previous manuscript must be a retained version of this paper")
                copy(source)
            put("retarget.md", "Previous venue: " + spec["previous_venue_id"] + "\nTarget venue: " + spec["target_venue_id"] + "\n\n" + "\n".join(spec["changes"]) + "\n")
            put("venue-fit.json", json.dumps(fit, ensure_ascii=False, indent=2) + "\n")
            cover = case.get("cover_letter", {})
            if not _nonempty(cover.get("text")) or not cover.get("evidence_sources"):
                raise ValueError("cover letter needs located contribution and venue-fit evidence")
            for source in cover["evidence_sources"]:
                _binding(project, source, located=True)
            put("cover-letter.txt", cover["text"] + "\n")
    if kind == "rebuttal":
        rows = case.get("rebuttal", [])
        if not rows:
            raise ValueError("rebuttal preparation needs anticipated concerns; never fabricate external reviews")
        for row in rows:
            if not all(_nonempty(row.get(k)) for k in ("id", "concern", "response")) or not row.get("evidence_sources"):
                raise ValueError("each anticipated concern needs an evidence-bound response")
            for source in row["evidence_sources"]:
                _binding(project, source, located=True)
        put("rebuttal-preparation.md", "Anticipated concerns; these are not received reviewer comments.\n\n" + "\n\n".join(r["id"] + ": " + r["concern"] + "\n" + r["response"] for r in rows) + "\n")
    if kind == "reproduction":
        _reproduction(project, paper_id, case.get("reproduction", {}), report, copy, put)
    if origins:
        from scripts.output_provenance import require_final_origins, ProvenanceError
        try:
            require_final_origins(project, origins)
        except ProvenanceError as exc:
            raise ValueError(str(exc)) from exc
    digest = hashlib.sha256(b"".join(name.encode() + b"\0" + files[name] for name in sorted(files))).hexdigest()
    root = path_in(project, f"papers/{paper_id}/release-preparation/{kind}-{digest}", exists=False)
    manifest = {"schema_version": "1.0", "paper_id": paper_id, "kind": kind, "content_sha256": digest,
                "external_publication": False, "scientific_validity_verified": False,
                "files": [{"path": name, "sha256": hashlib.sha256(payload).hexdigest()} for name, payload in sorted(files.items())]}
    if root.exists():
        manifest_path = path_in(project, (root / "manifest.json").relative_to(project).as_posix())
        previous = read(manifest_path)
        from scripts.output_provenance import current_origin
        inventory = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() or p.is_symlink()}
        if ({k: v for k, v in previous.items() if k != "prepared_at"} != manifest
                or current_origin(project, manifest_path).get("status") != "tracked"
                or inventory != {f["path"] for f in manifest["files"]} | {"manifest.json"}
                or any(sha(path_in(project, (root / f["path"]).relative_to(project).as_posix())) != f["sha256"] for f in manifest["files"])):
            raise ValueError("existing release snapshot changed; never overwrite historical versions")
        manifest = previous
    else:
        manifest["prepared_at"] = datetime.now(timezone.utc).isoformat()
        for name, payload in files.items():
            target = path_in(project, (root / name).relative_to(project).as_posix(), exists=False)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        write(root / "manifest.json", manifest)
        record(project, [root / name for name in files] + [root / "manifest.json"], "scripts/research_case.py")
    return {**manifest, "path": root.relative_to(project).as_posix()}


def _reproduction(project, paper_id, spec, report, copy, put):
    """Export an already executed replay unit, never a made-up run command."""
    from scripts.primary_recovery import selected_attempt, receipt
    plan_path = artifact_path(project, "experiments/plan.json", paper_id)
    registry_path = artifact_path(project, "experiments/registry.jsonl", paper_id)
    plan = read(plan_path)
    registry = [json.loads(line) for line in registry_path.read_text().splitlines() if line.strip()]
    from scripts.results_validation import validate_registry
    errors = validate_registry(project, plan, registry)
    if errors:
        raise ValueError("reproduction requires unchanged approved executor evidence: " + "; ".join(errors))
    run = next((r for r in plan["runs"] if r["run_id"] == spec.get("replay_run_id") and r["paper_id"] == paper_id), None)
    if run is None:
        raise ValueError("reproduction needs this paper's actual approved replay run")
    attempt = selected_attempt(project, run["run_id"], registry, plan_sha256=sha(plan_path))
    if not attempt or attempt.get("status") != "succeeded":
        raise ValueError("reproduction command must have an actual successful executor attempt")
    # The shared registry validator binds command, cwd, seed, inputs and outputs;
    # bind that same record to the runner's original receipt before export.
    receipt(project, attempt)
    isolation, recorded = run.get("isolation", {}), attempt.get("executor_isolation", {})
    container = isolation.get("kind") == "container"
    if run.get("runtime") or recorded.get("reviewed_runtime"):
        raise ValueError("minimal replay excludes separately mounted study toolchains; use study_routes.export_results for their complete result exports")
    if recorded.get("kind") != isolation.get("kind") or isolation.get("kind") not in {"host", "container"}:
        raise ValueError("portable replay needs matching recorded host or Docker isolation")
    resources = None
    if container:
        from scripts.experiment_runner import requested_resources
        resources = requested_resources(run)
        image = isolation.get("image", "")
        if (isolation.get("engine") != "docker" or not re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", image)
                or any(recorded.get(key) != isolation.get(key) for key in ("engine", "image"))
                or recorded.get("image_digest") != image.rsplit("@sha256:", 1)[-1]
                or any(recorded.get(key) is not True for key in ("isolated_executor", "network_disabled", "read_only_root"))
                or attempt.get("resource_allocation", {}).get("requested") != resources
                or attempt.get("resource_allocation", {}).get("container_limits_configured") is not True):
            raise ValueError("Docker replay needs the actual pinned image, isolation and frozen resource allocation")
    license_name = copy(spec.get("license", {}))
    environment = spec.get("environment", {})
    environment_path = _binding(project, environment)
    if not any(all(item.get(key) == environment.get(key) for key in ("path", "sha256")) for item in run.get("inputs", [])):
        raise ValueError("environment lock must be a frozen input of the actual replay run")
    python_version = attempt.get("runtime", {}).get("python")
    pins = [line.strip() for line in environment_path.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")]
    python_pins = [pin for pin in pins if re.fullmatch(r"python==[0-9]+\.[0-9]+\.[0-9]+", pin)]
    if (len(python_pins) > 1 or (not container and (len(python_pins) != 1 or not python_version or "python==" + python_version not in pins))
            or any(pin.startswith("python==") and pin not in python_pins for pin in pins)
            or any(not re.fullmatch(r"[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==[A-Za-z0-9_.+!-]+", pin) for pin in pins)):
        raise ValueError("environment lock needs exact supplied package pins; host replay needs its recorded Python version")
    environment_name = copy(environment)
    dependency_pins = [pin for pin in pins if not pin.startswith("python==")]
    put("requirements.txt", "\n".join(dependency_pins) + "\n")
    put("recorded-runtime.json", json.dumps({"run_id": run["run_id"], "attempt_id": attempt.get("attempt_id"),
        "runtime": ({"engine": "docker", "image": isolation["image"], "image_digest": recorded["image_digest"]} if container
                    else {k: attempt.get("runtime", {}).get(k) for k in ("python", "platform")}),
        "environment_authority": "recorded_digest_pinned_image" if container else "recorded_host_interpreter",
        "environment_lock": environment, "dependency_installation_verified": False}, indent=2) + "\n")
    supplied = spec.get("files", [])
    paths = set()
    for source in supplied:
        if not _nonempty(source.get("license")):
            raise ValueError("reproduction files require redistribution license evidence")
        _binding(project, source.get("rights_source"), located=True)
        copy(source)
        paths.add(source["path"])
    frozen_paths = {i["path"] for i in run.get("inputs", [])}
    if not frozen_paths <= paths | {environment["path"]}:
        raise ValueError("reproduction unit omits frozen replay inputs")
    for binding in run.get("inputs", []):
        _binding(project, binding)
    # A native replay unit must actually have emitted a result table. Its declared
    # comparison coverage is checked against all results, including negative ones.
    outputs = {o["path"] for o in attempt.get("outputs", [])}
    table = spec.get("result_table")
    if table not in outputs:
        raise ValueError("result_table was not emitted by the recorded replay run")
    result_binding = next(output for output in attempt["outputs"] if output["path"] == table)
    copy(result_binding, executed=True)
    rows = list(csv.DictReader(io.StringIO(path_in(project, table).read_text())))
    expected = {r["comparison_id"] for r in report.get("comparisons", [])}
    if not expected or len(rows) != len(expected) or {r.get("comparison_id") for r in rows} != expected:
        raise ValueError("replayed result table must retain every registered comparison")
    for row in rows:
        actual = next(r for r in report["comparisons"] if r["comparison_id"] == row["comparison_id"])
        for key in ("estimate", "ci_low", "ci_high", "decision"):
            if str(row.get(key)) != str(actual.get(key)):
                raise ValueError("replayed result table differs from executor evidence: " + key)
    cwd = run.get("cwd", ".")
    if Path(cwd).is_absolute() or ".." in Path(cwd).parts:
        raise ValueError("replay cwd must remain inside the portable package")
    argv = run["argv"]
    if (len(argv) < 2 or argv[0] not in {"python", "python3"} or argv[1].startswith("-")
            or any(Path(arg).is_absolute() or ".." in Path(arg).parts or "\\" in arg for arg in argv)):
        raise ValueError("minimal replay currently supports a portable recorded Python argv")
    if (Path(cwd) / argv[1]).as_posix() not in paths & frozen_paths:
        raise ValueError("recorded replay script must be one of the exported frozen inputs")
    output_dirs = sorted({str(Path(output).parent) for output in outputs})
    if container:
        replay = {"image": isolation["image"], "argv": argv, "cwd": cwd, "seed": run["seed"],
            "run_id": run["run_id"], "timeout_seconds": run["timeout_seconds"], "resources": resources,
            "inputs": run["inputs"], "outputs": sorted(outputs), "result_table": result_binding}
        put("replay-run.json", json.dumps(replay, indent=2) + "\n")
        put("reproduce.py", _DOCKER_REPLAY)
        instructions = ("Load the recorded image with `docker pull " + isolation["image"] + "` on a compatible POSIX Docker host. "
            "Then run `python reproduce.py`. The replay uses --pull=never, the exact recorded image/argv/seed/resource limits, "
            "no network, read-only inputs and only the registered output files as writable mounts. It checks every input and the result-table hash. "
            "The table script must support those existing file mounts; replacing an output by renaming another file is not supported. "
            "The frozen declaration in `" + environment_name + "` is retained; the image digest is the container environment identity. "
            "An unknown Python version may remain omitted; historical installed dependencies were not independently verified. "
            "No host Python version is presented as the container's interpreter. Separately mounted study toolchains are excluded.")
    else:
        put("reproduce.py", "import hashlib, importlib.metadata, os, pathlib, platform, subprocess, sys\n"
        + "root = pathlib.Path(__file__).resolve().parent / 'sources'\n"
        + "if platform.python_version() != " + repr(python_version) + ": raise SystemExit('Use the recorded Python version.')\n"
        + "for pin in " + repr(dependency_pins) + ":\n name, version = pin.split('==')\n"
        + " if importlib.metadata.version(name.split('[')[0]) != version: raise SystemExit('Install requirements.txt: ' + name)\n"
        + "for directory in " + repr(output_dirs) + ": (root / directory).mkdir(parents=True, exist_ok=True)\n"
        + "environment = {**os.environ, **" + repr({"RESEARCH_OS_RUN_ID": run["run_id"], "RESEARCH_OS_SEED": str(run["seed"]), "PYTHONHASHSEED": str(run["seed"])}) + "}\n"
        + "subprocess.run([sys.executable, *" + repr(argv[1:]) + "], cwd=root / " + repr(cwd) + ", env=environment, timeout=" + repr(run["timeout_seconds"]) + ", check=True)\n"
        + "if hashlib.sha256((root / " + repr(table) + ").read_bytes()).hexdigest() != " + repr(result_binding["sha256"]) + ": raise SystemExit('Replay table differs from the recorded result.')\n")
        instructions = ("Install the exact environment in `" + environment_name
            + "`. Use its Python version and `python -m pip install -r requirements.txt`. The lock was a frozen run input; recorded-runtime.json retains the actual runner Python/platform. Historical installed dependency versions were not independently captured. Run `python reproduce.py` from this directory to verify the environment, rerun the recorded result-table unit and compare its exact output hash.")
    put("README.md", "# Local reproduction package\n\n" + instructions + "\n\n"
        + "License: `" + license_name + "`. All registered comparisons are in results.csv; failures and inconclusive decisions remain visible in results.json.\n"
        + "This package was prepared locally, not uploaded. Replay success does not establish scientific validity.\n")


_DOCKER_REPLAY = '''import hashlib, json, os, pathlib, subprocess, uuid
folder = pathlib.Path(__file__).resolve().parent
root = folder / 'sources'
run = json.loads((folder / 'replay-run.json').read_text())
if not hasattr(os, 'getuid'): raise SystemExit('Use a compatible POSIX Docker host.')
def target(relative):
    path = root / relative
    if pathlib.Path(relative).is_absolute() or '..' in pathlib.Path(relative).parts or any(c in str(path) for c in (',', ':', '\\\\')):
        raise SystemExit('Unsafe replay path.')
    if any(item.is_symlink() for item in (path, *path.parents)) or not path.resolve().is_relative_to(root.resolve()):
        raise SystemExit('Replay paths must stay inside the package without symlinks.')
    return path
for item in run['inputs']:
    if hashlib.sha256(target(item['path']).read_bytes()).hexdigest() != item['sha256']:
        raise SystemExit('Replay input differs from its frozen hash: ' + item['path'])
resources = run['resources']
memory = f"{resources['memory_gb']:g}g" if float(resources['memory_gb']).is_integer() else str(int(resources['memory_gb'] * 1024**3))
container_name = 'lunwen-replay-' + uuid.uuid4().hex
command = ['docker', 'run', '--rm', '--pull=never', '--name', container_name, '--user', f'{os.getuid()}:{os.getgid()}',
    '--network=none', '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=512m',
    '--security-opt', 'no-new-privileges', '--cap-drop=ALL', '--pids-limit=256',
    f"--cpus={resources['cpu']:g}", '--memory=' + memory,
    '-v', str(root.resolve()) + ':/workspace:ro', '-w', '/workspace' + ('/' + run['cwd'] if run['cwd'] != '.' else '')]
if resources['gpu']: command.extend(['--gpus', 'count=' + str(resources['gpu'])])
for item in run['inputs']:
    command.extend(['--mount', 'type=bind,src=' + str(target(item['path'])) + ',dst=/workspace/' + item['path'] + ',readonly'])
for relative in run['outputs']:
    path = target(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'')
    command.extend(['--mount', 'type=bind,src=' + str(path) + ',dst=/workspace/' + relative])
for key, value in {'RESEARCH_OS_RUN_ID': run['run_id'], 'RESEARCH_OS_SEED': str(run['seed']), 'PYTHONHASHSEED': str(run['seed'])}.items():
    command.extend(['-e', key + '=' + value])
try:
    subprocess.run(command + [run['image'], *run['argv']], check=True, timeout=run['timeout_seconds'])
finally:
    cleanup = subprocess.run(['docker', 'rm', '-f', container_name], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=30)
    if cleanup.returncode and 'No such container' not in cleanup.stderr:
        raise SystemExit('Could not remove this replay container: ' + container_name + ': ' + cleanup.stderr)
result = run['result_table']
if hashlib.sha256(target(result['path']).read_bytes()).hexdigest() != result['sha256']:
    raise SystemExit('Replay table differs from the recorded result.')
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--paper", required=True)
    parser.add_argument("--export", choices=sorted(KINDS))
    args = parser.parse_args()
    result = export(args.project, args.paper, args.export) if args.export else build_packet(args.project, args.paper)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
