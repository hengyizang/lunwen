"""Source-bound CCFA scientific extensions on the existing cloud control plane.

These are deterministic report builders, not another runner, approval system,
research-state store, model evaluator or scientific acceptance score.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

from scripts import output_provenance
from scripts.research_artifacts import path_in, read, record, sha, write

OPERATIONS = {"continuity", "lineage", "novelty_watch", "exemplar", "internal_review"}
PREFIX = "reports/ccfa-science"
MODULE = "scripts/ccfa_science.py"
LIMITS = {"paid_calls": 0, "experiments_executed": 0, "gate_approved": False,
          "scientific_completion_verified": False, "human_scientific_review_required": True,
          "ongoing_monitoring_installed": False}
EXEMPLAR_MOVES = {"story", "abstract", "introduction", "method", "evidence", "citations", "reusable_techniques"}
ISSUE_STATES = {"unresolved", "partially_resolved", "resolved", "not_applicable"}


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _keys(value, allowed, required=(), label="input"):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise ValueError(label + " has missing or unsupported fields")


def _text(value, label, maximum=6000):
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or "\x00" in value or value.strip().casefold() in {"todo", "tbd", "unknown", "n/a"}):
        raise ValueError("concrete bounded " + label + " required")
    return value.strip()


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value):
        raise ValueError("bounded identifier required")
    return value


def _rows(value, label, minimum=1, maximum=100):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{label} requires {minimum}..{maximum} entries")
    return value


def _strings(value, label, minimum=1):
    items = [_text(v, label, 2000) for v in _rows(value, label, minimum)]
    if len(set(items)) != len(items):
        raise ValueError(label + " contains duplicates")
    return items


def _time(value):
    value = _text(value, "dated evidence", 100)
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None or instant > datetime.now(timezone.utc):
        raise ValueError("evidence needs a past timezone-aware timestamp")
    return value


def _bind(project, value, *, tracked=False):
    _keys(value, {"path", "sha256"}, {"path", "sha256"}, "file binding")
    relative = value["path"]
    if (not isinstance(relative, str) or not relative.startswith(("program/", "papers/", "evidence/", "literature/", "results/", "experiments/", "reports/"))
            or relative.startswith(PREFIX + "/") or any(p.casefold() in {
                "state", "raw", "private", "secrets", "credentials", ".git", "submission"} for p in Path(relative).parts)):
        raise ValueError("source is outside the bounded public project corpus")
    target = path_in(project, relative)
    if target.stat().st_size < 1 or target.stat().st_size > 64_000_000:
        raise ValueError("bounded nonempty source required")
    if value["sha256"] != sha(target):
        raise ValueError("source hash is stale: " + relative)
    origin = output_provenance.current_origin(project, target)
    if origin.get("family") == "anthropic" or (tracked and origin.get("status") != "tracked"):
        raise ValueError("source requires current non-Claude writer provenance")
    return {"path": relative, "sha256": value["sha256"], "origin": origin}


def _remember(bindings, item):
    prior = next((b for b in bindings if b["path"] == item["path"]), None)
    if prior and prior != item:
        raise ValueError("conflicting versions of the same source")
    if not prior:
        bindings.append(item)
    return item


def _file(project, value, bindings, *, tracked=False):
    return _remember(bindings, _bind(project, value, tracked=tracked))


def _anchor(project, value, bindings, *, paths=None):
    from scripts.research_candidates import anchor_errors
    _keys(value, {"path", "sha256", "locator", "excerpt", "pdf_page"},
          {"path", "sha256", "locator", "excerpt"}, "located evidence")
    if paths is not None and value["path"] not in paths:
        raise ValueError("evidence must locate the declared source version")
    _file(project, {k: value[k] for k in ("path", "sha256")}, bindings)
    errors = anchor_errors(project, value)
    if errors:
        raise ValueError("; ".join(errors))
    return dict(value)


def _anchors(project, value, bindings, *, paths=None):
    return [_anchor(project, a, bindings, paths=paths) for a in _rows(value, "located evidence", 1, 30)]


def _scope(project, value, bindings):
    question = _text(value.get("doctoral_question"), "doctoral question", 4000)
    ids = _strings(value.get("paper_ids", []), "paper scope", 0)
    if any(i not in {f"P{n:02d}" for n in range(1, 7)} for i in ids):
        raise ValueError("paper scope is restricted to P01-P06")
    core = path_in(project, "program/core-thesis.json", exists=False)
    status = "proposed_requires_G1_G2_human_review"
    if core.is_file():
        _file(project, {"path": "program/core-thesis.json", "sha256": sha(core)}, bindings)
        canonical = read(core).get("doctoral_question")
        if isinstance(canonical, str) and canonical.strip() and canonical.strip().casefold() not in {"unassigned", "tbd", "unknown"}:
            if canonical.strip() != question:
                raise ValueError("scope differs from the current doctoral question; human G1/G2 review required")
            status = "current_question_bound_not_gate_approval"
    return {"doctoral_question": question, "paper_ids": ids, "status": status}


def _check(project, value, artifact, bindings):
    """Only a current native deterministic passed report can back verification."""
    binding = _file(project, value, bindings, tracked=True)
    origin = binding["origin"]
    if (origin.get("family") != "other" or origin.get("provider") != "deterministic-control-plane"
            or origin.get("model") not in {"scripts/literature_workbench.py", "scripts/literature_reasoning.py",
                "scripts/research_candidates.py", "scripts/research_extensions.py", "scripts/revision_integrity.py",
                "scripts/experiment_runner.py", "scripts/ref_verify.py"}):
        raise ValueError("verification needs a native deterministic check, not an authored assertion")
    report = read(path_in(project, binding["path"]))
    if report.get("pass") is not True and report.get("passed") is not True:
        raise ValueError("check did not explicitly pass")
    found = any(isinstance(row, dict) and row.get("path") == artifact["path"]
                and row.get("sha256") == artifact["sha256"]
                for group in ("inputs", "outputs", "sources") for row in report.get(group, []))
    if not found:
        raise ValueError("check does not bind the current artifact hash")
    for name in ("inputs", "outputs", "sources"):
        for row in _rows(report.get(name, []), "native check dependencies", 0, 300):
            if isinstance(row, dict) and "path" in row and "sha256" in row:
                _file(project, {k: row[k] for k in ("path", "sha256")}, bindings)
    return {"path": binding["path"], "sha256": binding["sha256"]}


def _continuity(project, data, previous, bindings, scope):
    _keys(data, {"goal_revision", "objective", "constraints", "acceptance", "authoritative_inputs", "route",
                 "next_action", "mode", "artifacts", "transition", "open_items"},
          {"goal_revision", "objective", "constraints", "acceptance", "authoritative_inputs", "route", "next_action", "mode", "artifacts", "open_items"}, "continuity")
    revision = data["goal_revision"]
    if type(revision) is not int or revision < 1 or data["mode"] not in {"normal", "focused", "reconciling"}:
        raise ValueError("valid goal revision and execution mode required")
    goal = {"revision": revision, "objective": _text(data["objective"], "objective"),
            "constraints": _strings(data["constraints"], "constraints"), "acceptance": _strings(data["acceptance"], "acceptance")}
    authoritative = [_file(project, row, bindings, tracked=True) for row in _rows(data["authoritative_inputs"], "authoritative inputs", 1, 30)]
    route = data["route"]
    _keys(route, {"id", "summary"}, {"id", "summary"}, "route")
    route = {"id": _id(route["id"]), "summary": _text(route["summary"], "route summary")}
    transition = data.get("transition")
    old = previous["result"] if previous else None
    goal_changed = old is not None and any(old["goal"][k] != goal[k] for k in ("objective", "constraints", "acceptance"))
    route_changed = old is not None and old["route"] != route
    recovering = old is not None and old["mode"] != "normal" and data["mode"] == "normal"
    if old and (revision < old["goal"]["revision"] or goal_changed and revision <= old["goal"]["revision"]):
        raise ValueError("a changed objective/acceptance needs a new goal revision")
    if goal_changed or route_changed or recovering:
        _keys(transition, {"basis", "reason", "evidence"}, {"basis", "reason", "evidence"}, "material transition")
        allowed = {"user_instruction", "intent_correction"} if goal_changed else {
            "user_instruction", "intent_correction", "new_evidence", "verified_failure", "comparison", "recovery_check"}
        if transition["basis"] not in allowed or recovering and transition["basis"] != "recovery_check":
            raise ValueError("transition basis does not justify the declared change")
        transition = {"basis": transition["basis"], "reason": _text(transition["reason"], "transition reason"),
                      "evidence": _anchors(project, transition["evidence"], bindings)}
        if old.get("transition") == transition:
            raise ValueError("an unchanged historical transition is not fresh change evidence")
    elif transition is not None:
        raise ValueError("transition supplied without a material transition")
    artifacts, seen = [], set()
    for row in _rows(data["artifacts"], "artifacts", 0):
        _keys(row, {"file", "status", "checks"}, {"file", "status"}, "artifact")
        item = _file(project, row["file"], bindings)
        if item["path"] in seen or row["status"] not in {"proposed", "executed", "verified"}:
            raise ValueError("unique artifacts and explicit truthful statuses required")
        seen.add(item["path"])
        checks = row.get("checks", [])
        if row["status"] == "verified":
            checks = [_check(project, c, item, bindings) for c in _rows(checks, "fresh artifact checks", 1, 20)]
        elif checks:
            raise ValueError("only verified artifacts carry checks")
        artifacts.append({"file": {"path": item["path"], "sha256": item["sha256"]}, "status": row["status"], "checks": checks})
    if old:
        removed = {a["file"]["path"] for a in old["artifacts"] if a["status"] == "verified"} - seen
        if removed:
            raise ValueError("retain verified artifacts; downgrade explicitly instead of silently retiring")
    return {"goal": goal, "authoritative_inputs": authoritative, "route": route, "mode": data["mode"],
            "next_action": _text(data["next_action"], "next action"), "open_items": _strings(data["open_items"], "open items", 0),
            "transition": transition, "artifacts": artifacts, "record_consistency_verified": True,
            "semantic_goal_preservation_verified": False, "replaces_existing_project_state": False}


def _lineage(project, data, previous, bindings, scope):
    _keys(data, {"candidates", "selected_candidate", "selection_reason"}, {"candidates"}, "lineage")
    candidates, known = [], {}
    for row in _rows(data["candidates"], "candidates", 1, 50):
        _keys(row, {"id", "parents", "operator", "premise", "new_inference", "inference_boundary", "mechanism_change", "component_necessity",
                    "discriminator", "conditions", "status", "evidence", "measurement"},
              {"id", "parents", "operator", "premise", "new_inference", "inference_boundary", "mechanism_change", "component_necessity", "discriminator", "conditions", "status", "evidence"}, "candidate")
        identifier = _id(row["id"])
        parents = [_id(p) for p in _rows(row["parents"], "candidate parents", 0, 10)]
        if identifier in known or len(set(parents)) != len(parents) or any(p not in known for p in parents):
            raise ValueError("lineage must be unique, acyclic and ordered parents before children")
        operator = row["operator"]
        if operator not in {"seed", "refine", "combine", "transfer", "invert", "instrument"} or (operator == "seed") != (not parents):
            raise ValueError("seed has no parent; every branch has named parents and a supported operator")
        if operator == "combine" and len(parents) < 2:
            raise ValueError("combine requires two distinct parents")
        if row["status"] not in {"exploratory", "proposed", "measured", "rejected", "refuted"}:
            raise ValueError("candidate status must separate proposed and measured")
        candidate = {"id": identifier, "parents": parents, "operator": operator, "status": row["status"],
            **{k: _text(row[k], "candidate " + k) for k in ("premise", "new_inference", "inference_boundary", "mechanism_change", "component_necessity", "discriminator")},
            "conditions": _strings(row["conditions"], "candidate conditions"), "evidence": _anchors(project, row["evidence"], bindings),
            "novelty_verified": False, "scientific_selection_verified": False}
        if row["status"] == "measured":
            measurement = row.get("measurement")
            _keys(measurement, {"receipt", "run_id", "configuration"}, {"receipt", "run_id", "configuration"}, "measurement")
            receipt = _file(project, measurement["receipt"], bindings)
            run = read(path_in(project, receipt["path"]))
            if (not re.fullmatch(r"experiments/runs/[A-Za-z0-9][A-Za-z0-9._-]{0,119}/run.json", receipt["path"])
                    or receipt["path"] != f"experiments/runs/{run.get('attempt_id')}/run.json"
                    or run.get("status") != "succeeded" or run.get("run_id") != measurement["run_id"]
                    or run.get("paper_id") not in set(scope["paper_ids"])
                    or not run.get("input_integrity", {}).get("passed") or not run.get("outputs")):
                raise ValueError("measured candidate requires a successful exact native experiment receipt")
            plan = path_in(project, "experiments/plan.json")
            if run.get("approved_plan_sha256") != sha(plan):
                raise ValueError("measurement plan changed")
            _file(project, {"path": "experiments/plan.json", "sha256": sha(plan)}, bindings)
            config = next((r for r in read(plan).get("runs", []) if r.get("run_id") == run["run_id"]), None)
            configuration = _file(project, measurement["configuration"], bindings)
            canonical_config = {k: configuration[k] for k in ("path", "sha256")}
            registry = path_in(project, "experiments/registry.jsonl")
            _file(project, {"path": "experiments/registry.jsonl", "sha256": sha(registry)}, bindings)
            attempts = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines() if line.strip()]
            if (not config or config.get("paper_id") != run.get("paper_id") or canonical_config not in config.get("inputs", [])
                    or not any(r.get("path") == configuration["path"] and r.get("sha256") == configuration["sha256"] for r in run.get("inputs", []))
                    or read(path_in(project, configuration["path"])).get("candidate_id") != identifier
                    or [r for r in attempts if r.get("run_id") == run["run_id"]] != [run]):
                raise ValueError("measurement needs its exact registered attempt and approved candidate configuration")
            for output in run["outputs"]:
                _file(project, {k: output[k] for k in ("path", "sha256")}, bindings)
            candidate["measurement"] = {"receipt": {"path": receipt["path"], "sha256": receipt["sha256"]}, "run_id": run["run_id"], "configuration": canonical_config}
        elif row.get("measurement") is not None:
            raise ValueError("unmeasured candidate cannot carry a measurement")
        known[identifier] = candidate
        candidates.append(candidate)
    old_ids = {r["id"] for r in previous["result"]["candidates"]} if previous else set()
    if old_ids - set(known):
        raise ValueError("preserve earlier branches and adverse outcomes")
    for old in previous["result"]["candidates"] if previous else []:
        if any(old[k] != known[old["id"]][k] for k in ("parents", "operator", "mechanism_change", "conditions", "discriminator")):
            raise ValueError("changed candidate mechanism/conditions needs a new child identifier")
    selected = data.get("selected_candidate")
    if selected is not None and selected not in known:
        raise ValueError("selected candidate is absent")
    reason = _text(data.get("selection_reason"), "selection rationale") if selected is not None else None
    if selected is None and data.get("selection_reason") is not None:
        raise ValueError("selection rationale needs a selected candidate")
    return {"candidates": candidates, "selected_candidate": selected, "selection_reason": reason,
            "measured_candidates": [r["id"] for r in candidates if r["status"] == "measured"],
            "best_measured_candidate": None, "best_requires_frozen_metric_and_comparable_experiment_audit": True,
            "conceptual_lineage_is_not_novelty_proof": True}


def _library(project, bindings, scope):
    from scripts import literature_workbench as wb
    library, _, manifest = wb._snapshot(project)
    if library.get("scope", {}).get("doctoral_question") != scope["doctoral_question"]:
        raise ValueError("workbench and CCFA report have different doctoral questions")
    for item in manifest.get("inputs", []):
        if item.get("kind") not in {"approved_binary_pdf", "approved_figure_asset"}:
            _file(project, {k: item[k] for k in ("path", "sha256")}, bindings)
    _file(project, {"path": manifest["output_dir"] + "/manifest.json", "sha256": sha(project / manifest["output_dir"] / "manifest.json")}, bindings, tracked=True)
    return {p["id"]: p for p in library["papers"]}, library


def _novelty_watch(project, data, previous, bindings, scope):
    _keys(data, {"window", "coverage_receipts", "claim_source", "findings"}, {"window", "coverage_receipts", "claim_source", "findings"}, "novelty watch")
    _keys(data["window"], {"from", "to"}, {"from", "to"}, "watch window")
    first, last = _time(data["window"]["from"]), _time(data["window"]["to"])
    if datetime.fromisoformat(first.replace("Z", "+00:00")) > datetime.fromisoformat(last.replace("Z", "+00:00")):
        raise ValueError("watch window is reversed")
    claims_binding = _file(project, data["claim_source"], bindings, tracked=True)
    if claims_binding["path"] != "program/novelty-claim-matrix.json":
        raise ValueError("watch claims must use the existing authoritative novelty claim matrix")
    matrix = read(path_in(project, claims_binding["path"]))
    claims = {c.get("claim_id", c.get("id")): c for c in matrix.get("claims", []) if isinstance(c, dict)}
    papers, library = _library(project, bindings, scope)
    receipts = []
    for row in _rows(data["coverage_receipts"], "executed search receipts", 1, 30):
        _keys(row, {"ledger", "receipt_id"}, {"ledger", "receipt_id"}, "search coverage")
        item = _file(project, row["ledger"], bindings)
        if item["path"] != "evidence/literature-api-ledger.jsonl":
            raise ValueError("coverage must use the existing provider ledger")
        records = [json.loads(line) for line in path_in(project, item["path"]).read_text(encoding="utf-8").splitlines() if line.strip()]
        matches = [r for r in records if r.get("receipt_id") == row["receipt_id"]]
        if len(matches) != 1 or matches[0].get("status") != "success" or matches[0].get("mode") != "live_search":
            raise ValueError("coverage needs one actual successful live search receipt")
        receipt = matches[0]
        instant = _time(receipt.get("completed_at"))
        parsed = lambda t: datetime.fromisoformat(t.replace("Z", "+00:00"))
        if not parsed(first) <= parsed(instant) <= parsed(last):
            raise ValueError("executed search receipt lies outside the declared watch window")
        normalized = {"path": receipt.get("normalized_results_path"), "sha256": receipt.get("normalized_results_sha256")}
        normalized_binding = _file(project, normalized, bindings)
        raw = receipt.get("raw_response_path")
        if not isinstance(raw, str) or not re.fullmatch(r"evidence/literature/raw/[A-Za-z0-9_-]+\.[A-Za-z0-9]+", raw):
            raise ValueError("raw provider receipt path is not native")
        raw_file = path_in(project, raw)
        if sha(raw_file) != receipt.get("response_sha256"):
            raise ValueError("raw provider response changed")
        _remember(bindings, {"path": raw, "sha256": sha(raw_file), "kind": "native_retrieval_raw"})
        receipts.append({"ledger": {"path": item["path"], "sha256": item["sha256"]}, "receipt_id": row["receipt_id"],
            "completed_at": instant, "normalized_results": {k: normalized_binding[k] for k in ("path", "sha256")},
            "query": receipt.get("query"), "actual_conditions": receipt.get("actual_conditions")})
    findings, ids = [], set()
    for row in _rows(data["findings"], "overlap findings", 0):
        _keys(row, {"id", "claim_id", "paper_id", "axes", "signal", "implication", "boundary", "claim_evidence", "source_evidence"},
              {"id", "claim_id", "paper_id", "axes", "signal", "implication", "boundary", "claim_evidence", "source_evidence"}, "overlap finding")
        identifier = _id(row["id"])
        paper = papers.get(row["paper_id"])
        if identifier in ids or row["claim_id"] not in claims or not paper or paper["status"] != "current":
            raise ValueError("overlap must name unique finding, current source and exact existing claim")
        if (not set(claims[row["claim_id"]].get("paper_ids", [])).intersection(scope["paper_ids"])
                or not set(paper.get("paper_ids", [])).intersection(scope["paper_ids"])):
            raise ValueError("overlap source and claim must serve this report's exact paper scope")
        ids.add(identifier)
        axes = _strings(row["axes"], "overlap axes")
        if set(axes) - {"problem", "mechanism", "evidence", "benchmark", "dataset", "claim", "positioning"} or row["signal"] not in {"RELAX", "RESEARCH", "FOLLOW-UP"}:
            raise ValueError("explicit supported overlap axes and signal required")
        source_paths = {paper["source"]["path"]}
        if paper.get("reader"):
            source_paths.add(paper["reader"]["path"])
        claim_evidence = _anchors(project, row["claim_evidence"], bindings, paths={claims_binding["path"]})
        claim_text = json.dumps(claims[row["claim_id"]], ensure_ascii=False)
        if any(a["excerpt"] not in claim_text for a in claim_evidence):
            raise ValueError("claim evidence quotes a different claim or matrix metadata")
        findings.append({"id": identifier, "claim_id": row["claim_id"], "paper_id": paper["id"], "axes": axes, "signal": row["signal"],
            "implication": _text(row["implication"], "claim-specific implication"), "boundary": _text(row["boundary"], "overlap inference boundary"),
            "claim_evidence": claim_evidence,
            "source_evidence": _anchors(project, row["source_evidence"], bindings, paths=source_paths),
            "source_scope": paper["source_scope"], "semantic_overlap_verified": False, "novelty_verified": False})
    old = {r["id"]: r for r in previous["result"]["findings"]} if previous else {}
    delta = {"new": [], "changed": [], "unchanged": [], "not_reobserved": sorted(set(old) - ids)}
    for finding in findings:
        delta["new" if finding["id"] not in old else "unchanged" if finding == old[finding["id"]] else "changed"].append(finding["id"])
    return {"window": {"from": first, "to": last}, "coverage_receipts": receipts,
            "findings": findings, "delta": delta, "empty_scan_proves_novelty": False,
            "search_coverage_independently_verified": False, "scope": library["scope"], "actions_are_proposals_only": True}


def _exemplar(project, data, previous, bindings, scope):
    from scripts import source_scope
    _keys(data, {"paper_id", "scope_record", "venue", "article_type", "moves", "do_not_copy", "selection_conditions"},
          {"paper_id", "scope_record", "article_type", "moves", "do_not_copy", "selection_conditions"}, "full-paper exemplar")
    papers, _ = _library(project, bindings, scope)
    paper = papers.get(data["paper_id"])
    if not paper or paper["status"] != "current" or paper.get("source_scope") == "metadata_only":
        raise ValueError("exemplar requires a current full source, not metadata")
    if not set(paper.get("paper_ids", [])).intersection(scope["paper_ids"]):
        raise ValueError("exemplar must match the declared paper scope")
    primary = {k: paper["source"][k] for k in ("path", "sha256")}
    errors = source_scope.verify(project, primary, data["scope_record"], "full_text")
    if errors:
        raise ValueError("; ".join(errors))
    _file(project, data["scope_record"], bindings, tracked=True)
    moves = data["moves"]
    _keys(moves, EXEMPLAR_MOVES, EXEMPLAR_MOVES, "exemplar moves")
    result = {}
    allowed = {primary["path"]}
    if paper.get("reader"):
        allowed.add(paper["reader"]["path"])
    for name in sorted(EXEMPLAR_MOVES):
        rows = []
        for row in _rows(moves[name], name + " moves", 1, 20):
            _keys(row, {"pattern", "purpose", "transfer_conditions", "evidence"}, {"pattern", "purpose", "transfer_conditions", "evidence"}, "writing move")
            rows.append({**{k: _text(row[k], "writing move " + k) for k in ("pattern", "purpose", "transfer_conditions")},
                "evidence": _anchors(project, row["evidence"], bindings, paths=allowed), "interpretation_is_not_source_claim": True})
        result[name] = rows
    venue = data.get("venue")
    if venue is not None:
        _keys(venue, {"name", "year", "evidence"}, {"name", "year", "evidence"}, "verified venue")
        if type(venue["year"]) is not int or not 1900 <= venue["year"] <= datetime.now(timezone.utc).year:
            raise ValueError("plausible verified venue year required")
        venue = {"name": _text(venue["name"], "venue", 300), "year": venue["year"], "evidence": _anchors(project, venue["evidence"], bindings, paths=allowed)}
    return {"paper_id": paper["id"], "primary_source": primary, "source_scope": "full_text_supplied_not_human_reading_certification",
            "scope_record": data["scope_record"], "venue": venue, "article_type": _text(data["article_type"], "article type", 300),
            "moves": result, "do_not_copy": _strings(data["do_not_copy"], "do-not-copy boundaries"),
            "selection_conditions": _strings(data["selection_conditions"], "exemplar selection conditions"),
            "global_defaults_changed": False, "human_reading_verified": False, "scientific_quality_verified": False}


def _criteria(value):
    result, ids = [], set()
    for row in _rows(value, "frozen review criteria", 1, 30):
        _keys(row, {"id", "criterion", "scope"}, {"id", "criterion", "scope"}, "criterion")
        identifier = _id(row["id"])
        if identifier in ids:
            raise ValueError("duplicate criterion")
        ids.add(identifier)
        result.append({"id": identifier, "criterion": _text(row["criterion"], "frozen criterion"), "scope": _text(row["scope"], "criterion scope")})
    return result


def _internal_review(project, data, previous, bindings, scope):
    _keys(data, {"historical", "current", "criteria", "readiness_criteria", "issues", "readiness", "scope"},
          {"historical", "current", "criteria", "readiness_criteria", "issues", "readiness", "scope"}, "internal review")
    historical, current_file = [_file(project, data[k], bindings, tracked=True) for k in ("historical", "current")]
    frozen, readiness_criteria = _criteria(data["criteria"]), _criteria(data["readiness_criteria"])
    for item in (historical, current_file):
        if not any(item["path"].startswith(f"papers/{p}/") for p in scope["paper_ids"]):
            raise ValueError("review manuscripts must lie within the declared paper scope")
    scope = _text(data["scope"], "review material scope")
    prior = previous["result"] if previous else None
    if prior and (prior["criteria"] != frozen or prior["readiness_criteria"] != readiness_criteria or prior["scope"] != scope
                  or prior["historical"] != {k: historical[k] for k in ("path", "sha256")}):
        raise ValueError("frozen comparison/readiness contract changed; use a separate noncomparable review identifier")
    criterion_ids = {r["id"] for r in frozen}
    inherited = {r["id"]: r for r in prior["issues"]} if prior else {}
    issues, ids = [], set()
    for row in _rows(data["issues"], "internal issues", 0, 300):
        _keys(row, {"id", "first_seen_version", "status", "origin", "applies_to", "dimensions", "severity", "finding", "evidence", "resolution"},
              {"id", "first_seen_version", "status", "origin", "applies_to", "dimensions", "severity", "finding", "evidence", "resolution"}, "internal issue")
        identifier = _id(row["id"])
        if identifier in ids or row["status"] not in ISSUE_STATES or row["origin"] not in {
                "inherited", "revision_regression", "previously_undetected", "newly_revealed_by_evidence"}:
            raise ValueError("unique stable issue ID, status and comparison provenance required")
        ids.add(identifier)
        if row["applies_to"] not in {"historical", "current", "both"} or row["severity"] not in {"blocker", "major", "minor"}:
            raise ValueError("issue applicability and severity required")
        if (row["origin"] == "revision_regression" and row["applies_to"] != "current"
                or row["origin"] == "previously_undetected" and row["applies_to"] != "both"):
            raise ValueError("latent historical issues apply to both; regressions apply to current")
        if identifier not in inherited and row["origin"] == "inherited":
            raise ValueError("new issue cannot claim inherited provenance")
        dimensions = _strings(row["dimensions"], "issue criteria")
        if set(dimensions) - criterion_ids:
            raise ValueError("issue changes an absent frozen criterion")
        first_seen = _text(row["first_seen_version"], "first seen version", 200)
        if identifier in inherited and (first_seen != inherited[identifier]["first_seen_version"] or dimensions != inherited[identifier]["dimensions"]
                                       or row["finding"] != inherited[identifier]["finding"]):
            raise ValueError("inherited issue definition changed")
        evidence = _anchors(project, row["evidence"], bindings)
        required_paths = {historical["path"]} if row["applies_to"] == "historical" else {current_file["path"]}
        if row["applies_to"] == "both":
            required_paths.add(historical["path"])
        if required_paths - {a["path"] for a in evidence}:
            raise ValueError("issue must anchor each applicable manuscript version")
        issues.append({"id": identifier, "first_seen_version": first_seen, "status": row["status"], "origin": row["origin"],
            "applies_to": row["applies_to"], "dimensions": dimensions, "severity": row["severity"],
            "finding": _text(row["finding"], "issue finding"), "evidence": evidence, "resolution": _text(row["resolution"], "resolution or unresolved work"),
            "semantic_resolution_verified": False})
    if set(inherited) - ids:
        raise ValueError("do not silently delete inherited issues")
    readiness, assessed = [], set()
    for row in _rows(data["readiness"], "readiness assessments", len(readiness_criteria), len(readiness_criteria)):
        _keys(row, {"criterion_id", "status", "rationale", "evidence"}, {"criterion_id", "status", "rationale", "evidence"}, "readiness assessment")
        cid = row["criterion_id"]
        if cid in assessed or cid not in {r["id"] for r in readiness_criteria} or row["status"] not in {"satisfied", "needs_revision", "blocked", "not_assessed"}:
            raise ValueError("exact categorical readiness criterion coverage required")
        assessed.add(cid)
        readiness.append({"criterion_id": cid, "status": row["status"], "rationale": _text(row["rationale"], "readiness rationale"),
                          "evidence": _anchors(project, row["evidence"], bindings, paths={current_file["path"]})})
    changed = []
    for issue in issues:
        prior_status = inherited.get(issue["id"], {}).get("status")
        if prior_status != issue["status"] or issue["id"] not in inherited:
            changed.append({"issue_id": issue["id"], "previous_status": prior_status, "current_status": issue["status"], "origin": issue["origin"]})
    improved = any(c["previous_status"] in {"unresolved", "partially_resolved"} and c["current_status"] in {"resolved", "not_applicable"} for c in changed)
    regressed = any(c["origin"] in {"revision_regression", "newly_revealed_by_evidence"} and c["current_status"] in {"unresolved", "partially_resolved"} or
                    c["previous_status"] in {"resolved", "not_applicable"} and c["current_status"] in {"unresolved", "partially_resolved"} for c in changed)
    progress = "mixed" if improved and regressed else "improved" if improved else "regressed" if regressed else "unchanged" if prior else "initial_review_no_historical_progress_claim"
    active = [i for i in issues if i["status"] in {"unresolved", "partially_resolved"} and i["applies_to"] != "historical"]
    statuses = {r["status"] for r in readiness}
    stance = "blocked" if "blocked" in statuses or any(i["severity"] == "blocker" for i in active) else "revise" if "needs_revision" in statuses or active else "not_assessed" if "not_assessed" in statuses else "ready_for_human_review"
    return {"review_type": "internal", "scope": scope, "historical": {k: historical[k] for k in ("path", "sha256")},
            "current": {k: current_file[k] for k in ("path", "sha256")}, "criteria": frozen, "readiness_criteria": readiness_criteria,
            "issues": issues, "changes": changed, "relative_progress": progress, "readiness": readiness,
            "current_readiness": stance, "acceptance_probability": None, "external_reviewer_round_created": False,
            "categorical_findings_require_independent_scientific_review": True}


BUILDERS = {"continuity": _continuity, "lineage": _lineage, "novelty_watch": _novelty_watch,
            "exemplar": _exemplar, "internal_review": _internal_review}


def _stored(project, operation, identifier):
    relative = f"{PREFIX}/{operation}/{identifier}.json"
    path = path_in(project, relative, exists=False)
    if not path.exists():
        return None, path
    origin = output_provenance.current_origin(project, path)
    if (origin.get("status") != "tracked" or origin.get("family") != "other"
            or origin.get("model") != MODULE or origin.get("provider") != "deterministic-control-plane"):
        raise ValueError("CCFA report has stale or incorrect native provenance")
    report = read(path)
    if report.get("operation") != operation or report.get("id") != identifier or report.get("schema_version") != "1.0":
        raise ValueError("CCFA report identity changed")
    return report, path


def current(project: Path, operation: str, identifier: str) -> dict:
    """Replay freshness of all inputs; a report is not a scientific certificate."""
    if operation not in OPERATIONS:
        raise ValueError("unsupported CCFA science operation")
    _id(identifier)
    report, path = _stored(project, operation, identifier)
    if report is None:
        raise ValueError("CCFA report is missing")
    if report.get("implementation_sha256") != sha(Path(__file__)):
        raise ValueError("CCFA implementation changed; rebuild affected report")
    scope_bindings = []
    if _scope(project, report["scope"], scope_bindings) != report["scope"] or any(b not in report["inputs"] for b in scope_bindings):
        raise ValueError("current doctoral scope changed; rebuild affected report")
    for binding in report["inputs"]:
        if binding.get("kind") == "native_retrieval_raw":
            if (not re.fullmatch(r"evidence/literature/raw/[A-Za-z0-9_-]+\.[A-Za-z0-9]+", binding["path"])
                    or sha(path_in(project, binding["path"])) != binding["sha256"]):
                raise ValueError("native retrieval raw response changed")
            continue
        observed = _bind(project, {k: binding[k] for k in ("path", "sha256")})
        if observed != binding:
            raise ValueError("CCFA input provenance changed; rebuild affected report")
    return report


def execute(project: Path, operation: str, request: dict) -> dict:
    """Build one of five native reports from an exact writer-authored input.

    request = {schema_version: '1.0', id, source, expected_source_sha256,
               expected_previous_sha256: null | latest report hash}
    """
    if os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1" and os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("CCFA science operations require the cloud executor")
    if operation not in OPERATIONS:
        raise ValueError("unsupported CCFA science operation")
    _keys(request, {"schema_version", "id", "source", "expected_source_sha256", "expected_previous_sha256"},
          {"schema_version", "id", "source", "expected_source_sha256", "expected_previous_sha256"}, "CCFA request")
    if request["schema_version"] != "1.0":
        raise ValueError("unsupported CCFA request schema")
    identifier = _id(request["id"])
    source = request["source"]
    if not isinstance(source, str) or not re.fullmatch(r"program/ccfa-inputs/[A-Za-z0-9_-]+\.json", source):
        raise ValueError("CCFA source must be one bounded JSON under program/ccfa-inputs")
    bindings = []
    source_binding = _file(project, {"path": source, "sha256": request["expected_source_sha256"]}, bindings, tracked=True)
    target = path_in(project, source)
    if target.stat().st_size > 2_000_000:
        raise ValueError("CCFA input exceeds 2 MB")
    from scripts.literature_workbench import _json
    value = _json(target.read_bytes())
    _keys(value, {"schema_version", "operation", "id", "doctoral_question", "paper_ids", "data"},
          {"schema_version", "operation", "id", "doctoral_question", "paper_ids", "data"}, "CCFA input")
    if value["schema_version"] != "1.0" or value["operation"] != operation or value["id"] != identifier:
        raise ValueError("CCFA input identity differs from the requested operation")
    previous, output = _stored(project, operation, identifier)
    if request["expected_previous_sha256"] != (sha(output) if previous else None):
        raise ValueError("previous CCFA report changed; reconcile before overwriting")
    if previous and previous.get("source") == source_binding:
        try:
            fresh = current(project, operation, identifier)
        except ValueError:
            fresh = None
        if fresh is not None:
            return {"path": output.relative_to(project).as_posix(), "sha256": sha(output), "reused": True, "report": fresh}
    scope = _scope(project, value, bindings)
    result = BUILDERS[operation](project, value["data"], previous, bindings, scope)
    if previous and previous["scope"]["doctoral_question"] != scope["doctoral_question"]:
        raise ValueError("a scope change needs a separate reviewed report identity")
    fingerprint = _digest({"operation": operation, "id": identifier, "scope": scope, "inputs": bindings,
                           "implementation": sha(Path(__file__)), "result": result})
    if previous and previous.get("input_fingerprint") == fingerprint:
        return {"path": output.relative_to(project).as_posix(), "sha256": sha(output), "reused": True, "report": previous}
    report = {"schema_version": "1.0", "operation": operation, "id": identifier, "scope": scope,
        "created_at": datetime.now(timezone.utc).isoformat(), "source": source_binding,
        "inputs": bindings, "implementation_sha256": sha(Path(__file__)), "input_fingerprint": fingerprint,
        "previous": {"path": f"{PREFIX}/history/{sha(output)}.json", "sha256": sha(output)} if previous else None,
        "result": result, "limits": dict(LIMITS)}
    outputs = []
    if previous:
        archive = path_in(project, report["previous"]["path"], exists=False)
        if archive.exists() and archive.read_bytes() != output.read_bytes():
            raise ValueError("immutable CCFA report history conflict")
        if not archive.exists():
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_bytes(output.read_bytes())
            outputs.append(archive)
    write(output, report)
    outputs.append(output)
    record(project, outputs, MODULE)
    return {"path": output.relative_to(project).as_posix(), "sha256": sha(output), "reused": False, "report": report}
