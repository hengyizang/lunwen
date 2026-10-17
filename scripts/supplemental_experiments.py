"""Separate, human-approved reviewer experiments inside the existing executor.

Each immutable scope has its own G3 protocol, budget, G4 registry and review.
Parent preregistration/approvals are never rewritten. No model or paid service
is called by these controls, and reviewer prose never authorizes execution.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from pathlib import Path

from scripts import experiment_runner as runner, research_quality as quality, study_routes
from scripts.research_artifacts import path_in, read, sha, write, record

PROPOSAL = "reviews/reviewer-required-experiment-plan.json"
PREFIX = "experiments/supplemental"
INDEX = "state/supplemental-experiments"


def need(condition, message):
    if not condition:
        raise ValueError(message)


def cloud():
    import os
    need(os.environ.get("DR_OS_CLOUD_EXECUTOR") == "1", "supplemental controls require the cloud executor")


def current(project, paper_id, *, execution=True):
    from scripts import reviewer_rounds
    state = read(project / "state/run.json")
    open_review = (state.get("gate") == "G5" and state.get("active_paper") == paper_id
                   and state.get("status") in ({"awaiting_work"} if execution else {"awaiting_work", "awaiting_approval", "approved"}))
    completed = (not execution and state.get("paper_statuses", {}).get(paper_id) == "submission_ready"
                 and f"G5:{paper_id}" in state.get("approved_gates", []))
    need(open_review or completed,
         "supplemental work requires this paper's open reviewer G5 round")
    index = reviewer_rounds._index(project, paper_id)
    need(bool(index["rounds"]), "a real external reviewer round is required")
    latest = index["rounds"][-1]
    manifest = read(project / latest["path"])
    intake = read(project / Path(latest["path"]).parent / "intake.json")
    need(intake.get("needs_new_experiments") is True, "the immutable review must request additional experiments")
    return manifest, intake


def candidate(project, paper_id):
    manifest, intake = current(project, paper_id)
    proposal_path = project / "papers" / paper_id / PROPOSAL
    value = read(proposal_path)
    scope = value.get("scope_id")
    need(isinstance(scope, str) and re.fullmatch(r"s[0-9]{3}", scope), "select a new s001-style supplemental scope")
    need(value.get("schema_version") == "1.0" and value.get("paper_id") == paper_id and value.get("round_id") == manifest["round_id"], "supplemental proposal belongs to another paper/round")
    comments = study_routes.ids(value.get("comment_ids"), "reviewer experiment comment IDs")
    need(comments <= {c["comment_id"] for c in intake["comments"]}, "supplemental protocol references unknown reviewer comments")
    dispositions = value.get("comment_dispositions")
    need(isinstance(dispositions, list) and len(dispositions) == len(intake["comments"])
         and {d.get("comment_id") for d in dispositions} == {c["comment_id"] for c in intake["comments"]}, "classify every immutable reviewer comment for experiment requirements")
    for disposition in dispositions:
        need(type(disposition.get("requires_experiment")) is bool, "explicit experiment disposition required")
        study_routes.text(disposition.get("rationale"), "comment experiment rationale")
    need(comments == {d["comment_id"] for d in dispositions if d["requires_experiment"]}, "scope must cover every comment classified as requiring an experiment")
    need(value.get("analysis_phase") in {"exploratory", "prospective_followup"} and value.get("prior_outcomes_seen") is True,
         "declare prior outcome access; supplemental work is not the original confirmatory study")
    for field in ("rationale", "outcome_access_statement", "scope_and_claim_limits"):
        study_routes.text(value.get(field), field)
    original_plan = project / "experiments/plan.json"
    original_prereg = project / "papers" / paper_id / "preregistration.json"
    need(sha(original_plan) == value.get("original_plan_sha256") and sha(original_prereg) == value.get("original_preregistration_sha256"), "original approved experiment inputs changed")
    state = read(project / "state/run.json")
    approval = next((a for a in reversed(state.get("approvals", [])) if a.get("gate") == "G3"), {})
    need(approval.get("experiment_plan_sha256") == sha(original_plan)
         and approval.get("frozen_protocol_sha256", {}).get(f"papers/{paper_id}/preregistration.json") == sha(original_prereg), "original G3 authority is absent or stale")
    errors = quality.validate_preregistration(read(original_prereg), paper_id, project)
    need(not errors, "; ".join(errors))
    root = path_in(project, f"{PREFIX}/{paper_id}/{manifest['round_id']}/{scope}", exists=False)
    control = path_in(project, f"{INDEX}/{paper_id}/{manifest['round_id']}/{scope}.json", exists=False)
    return value, root, control


def prepare(project, paper_id):
    """Initialize an unapproved candidate and copy only declared existing data."""
    cloud()
    value, child, control = candidate(project, paper_id)
    need(not control.is_file(), "approved supplemental scopes are immutable; propose a new scope")
    child.mkdir(parents=True, exist_ok=True)
    state_path = child / "state/run.json"
    if not state_path.is_file():
        write(state_path, {"schema_version": "2.0", "project": child.name, "stage_index": 3,
            "stage": "experiment-design", "gate": "G3", "status": "awaiting_work", "active_paper": paper_id,
            "paper_count": 1, "paper_statuses": {paper_id: "active"}, "approved_gates": [], "approvals": [], "history": []})
    need(read(state_path).get("gate") == "G3" and not read(state_path).get("approvals"), "candidate state is not an unapproved design")
    state = read(state_path)
    state["supplemental_context"] = {"parent_project": project.name, "paper_id": paper_id, "round_id": value["round_id"],
                                     "scope_id": value["scope_id"], "analysis_phase": value["analysis_phase"], "prior_outcomes_seen": True}
    write(state_path, state)
    imports = value.get("imports", [])
    need(isinstance(imports, list) and len(imports) <= 1000, "bounded declared imports required")
    for item in imports:
        source = path_in(project, item["source"])
        target = path_in(child, item["target"], exists=False)
        need(item["source"].startswith(("data/", "evidence/")) and item["target"].startswith(("data/", "evidence/"))
             and source.is_file() and sha(source) == item["sha256"], "only exact existing data/evidence may be imported")
        need(not any(part in {"acquisition", "quality"} for part in Path(item["target"]).parts), "regenerate scope-specific quality and rights receipts")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    # Reuse the same deterministic builders without giving the model permission
    # to write the child state, data confirmations, registry or runtime outputs.
    from scripts.cloud_research_steps import after_write
    after_write(child, "experiment-design")
    return {"status": "candidate_only", "scope": child.relative_to(project).as_posix(), "execution_authorized": False}


def _design_errors(child, paper_id):
    from scripts.research_design import validate_experiment_design
    plan = read(child / "experiments/plan.json")
    errors = runner.validate_plan(plan)
    context = read(child / "state/run.json").get("supplemental_context", {})
    expected_phase = "exploratory" if context.get("analysis_phase") == "exploratory" else "confirmatory"
    budget = runner.budget_ceiling(read(child / "experiments/budget.json"))
    need(all(r["paper_id"] == paper_id for r in plan["runs"]), "supplemental scope must contain only the selected paper")
    if study_routes.route(child, paper_id) == "empirical":
        designs = sorted((child / "papers" / paper_id / "experiments").glob("*.json"))
        need(bool(designs), "supplemental empirical experiment designs required")
        runs = {r["run_id"]: r for r in plan["runs"]}
        assigned = []
        for path in designs:
            value = read(path); errors.extend(validate_experiment_design(value, paper_id, runs)); assigned.extend(value["run_ids"])
            contract = read(child / "papers" / paper_id / "paper-contract.json")
            hypotheses = {h["id"] for h in contract.get("hypotheses", [])}
            need(set(value["hypothesis_ids"]) <= hypotheses, "supplemental design references uncontracted hypotheses")
            need(set(value["data_protocol"]["datasets"]) <= set(contract.get("datasets", [])) <= set(quality._manifest_map(child)), "supplemental data/design/manifest assignments differ")
        need(len(assigned) == len(set(assigned)) and set(assigned) == set(runs), "every supplemental run needs exactly one full experiment design")
        contract = read(child / "papers" / paper_id / "paper-contract.json")
        need({read(p)["design_id"] for p in designs} == set(contract.get("planned_experiments", {}).get("design_ids", [])), "supplemental design IDs differ from the scoped contract")
        protocol = read(child / "papers" / paper_id / "experiment-evidence-plan.json")
        phases = {c["analysis_phase"] for c in protocol["comparisons"]}
        need(phases == {expected_phase}, "supplemental analyses must retain the approved exploratory/prospective phase")
    elif study_routes.route(child, paper_id) == "meta_analysis":
        protocol = read(study_routes.protocol_path(child, paper_id))
        need({o["analysis_phase"] for o in protocol["outcomes"]} == {expected_phase}, "supplemental Meta outcomes must retain their approved exploratory/prospective phase")
    for run in plan["runs"]:
        need(run["isolation"]["kind"] == "container" and run["isolation"].get("engine") == "docker" and run["timeout_seconds"] <= 1200
             and all(p.startswith("results/") for p in run["expected_outputs"]), "supplemental cloud runs need pinned Docker, <=1200 seconds and results/ outputs")
    return plan, budget, errors


def prepare_approval(project, paper_id, actor):
    cloud()
    value, child, control = candidate(project, paper_id)
    need(not control.exists(), "scope already approved; never replace an old supplemental approval")
    state = read(child / "state/run.json")
    need(state.get("stage") == "experiment-design" and not state.get("approvals"), "an initialized, unapproved supplemental candidate is required")
    need(state.get("supplemental_context", {}).get("analysis_phase") == value["analysis_phase"], "supplemental phase changed after preparation")
    need(not (child / "experiments/registry.jsonl").exists() or not (child / "experiments/registry.jsonl").read_text().strip(), "cannot approve a protocol after experiment attempts exist")
    plan, budget, errors = _design_errors(child, paper_id)
    parent_claims = set(read(project / "papers" / paper_id / "paper-contract.json").get("independence", {}).get("unique_claim_ids", []))
    child_claims = set(read(child / "papers" / paper_id / "paper-contract.json").get("independence", {}).get("unique_claim_ids", []))
    need(bool(child_claims) and child_claims <= parent_claims, "supplemental claims must belong to the unchanged parent paper contract")
    constraints = read(project / "intake/constraints.json")
    cap = constraints.get("cloud_compute_budget_usd")
    need(type(cap) in (float, int) and math.isfinite(cap) and cap >= 0, "explicit parent compute authorization required")
    need(budget <= cap and sum(r["estimated_cost_usd"] for r in plan["runs"]) <= budget, "supplemental budget exceeds owner compute authorization")
    # The owner is explicitly reviewing these newly generated data reports in
    # this dossier; no model-supplied confirmation is copied or trusted.
    confirmations = []
    for dataset in quality._manifest_map(child):
        from scripts.dataset_fetch import validate_manifest
        manifest = quality._manifest_map(child)[dataset]
        errors.extend(validate_manifest(manifest))
        need(manifest.get("license", {}).get("confirmed_by_human") is True and manifest.get("download", {}).get("sha256") != "pending", "supplemental data rights and exact acquisition hashes need human confirmation")
        path = child / "data/quality" / f"{dataset}.json"
        need(path.is_file(), "supplemental data needs a complete quality report")
        errors.extend(quality.validate_data_quality_report(read(path), dataset, child))
        confirmations.append((child / "data/quality" / f"{dataset}-confirmation.json",
                              quality.create_data_quality_confirmation(child, dataset, actor)))
    # Prepare on an isolated copy so a read-only dossier cannot create human
    # confirmations, preregistrations or execution authority.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="supplemental-review-") as directory:
        preview = Path(directory) / child.name
        shutil.copytree(child, preview)
        for path, payload in confirmations:
            write(preview / path.relative_to(child), payload)
        errors.extend(quality.validate_g3_quality(preview, require_preregistration=False))
        need(not errors, "; ".join(errors))
        frozen = quality.create_preregistration(preview, paper_id, actor)
    return value, child, control, confirmations, frozen


def approve(project, paper_id, actor, review_sha256, run_id):
    value, child, control, confirmations, frozen = prepare_approval(project, paper_id, actor)
    for path, payload in confirmations:
        write(path, payload)
    # Confirmation content is time-bound: freeze the actual committed files,
    # rather than hashes of the temporary preview's different path tree.
    frozen = quality.create_preregistration(child, paper_id, actor)
    prereg_path = child / "papers" / paper_id / "preregistration.json"
    write(prereg_path, frozen)
    plan_path, budget_path = child / "experiments/plan.json", child / "experiments/budget.json"
    state = read(child / "state/run.json")
    approval = {"gate": "G3", "actor": actor, "cloud_review_sha256": review_sha256, "source_run_id": run_id,
                "experiment_plan_sha256": sha(plan_path), "experiment_budget_sha256": sha(budget_path),
                "frozen_protocol_sha256": {f"papers/{paper_id}/preregistration.json": sha(prereg_path)}}
    state.update(stage_index=4, stage="experiment-execution", gate="G4", status="awaiting_work", approved_gates=["G3"], approvals=[approval])
    write(child / "state/run.json", state)
    payload = {"schema_version": "1.0", "paper_id": paper_id, "round_id": value["round_id"], "scope_id": value["scope_id"],
               "scope_root": child.relative_to(project).as_posix(), "actor": actor, "source_run_id": run_id,
               "cloud_review_sha256": review_sha256, "proposal": value, "original_g3_unchanged": True,
               "approval": approval, "child_state_sha256": sha(child / "state/run.json"), "confirmation": None}
    write(control, payload)
    record(project, [control, child / "state/run.json", prereg_path, *[p for p, _ in confirmations]], "scripts/supplemental_experiments.py")
    return payload


def controls(project, paper_id, round_id):
    directory = project / INDEX / paper_id / round_id
    values = [(p, read(p)) for p in sorted(directory.glob("s[0-9][0-9][0-9].json"))]
    need(len(values) <= 100, "supplemental history exceeds its bounded review scope")
    registered = {v["scope_root"] for _, v in values}
    for child in (project / PREFIX / paper_id / round_id).glob("s[0-9][0-9][0-9]"):
        state = child / "state/run.json"
        registry = child / "experiments/registry.jsonl"
        if (state.is_file() and read(state).get("approvals")) or (registry.is_file() and registry.read_text().strip()):
            need(child.relative_to(project).as_posix() in registered, "orphaned supplemental approval or attempts cannot be omitted")
    return values


def review_binding(project, paper_id, round_ids):
    """Bind current supplemental authority and evidence into the parent G5 hash.

    This read-only inventory remains stable when the parent moves to approval
    or packaging. Changes to child approvals, attempts, results or manuscript
    mappings invalidate the old reviewer audit and final human approval.
    """
    from scripts.cloud_checkpoint import excluded
    scopes = []
    for round_id in round_ids:
        for control_path, control in controls(project, paper_id, round_id):
            child = path_in(project, control["scope_root"], exists=False)
            need(child.is_dir(), "approved supplemental study is missing")
            relative_paths = {"state/run.json", "experiments/plan.json", "experiments/budget.json",
                              "experiments/registry.jsonl", f"papers/{paper_id}/preregistration.json",
                              f"papers/{paper_id}/experiment-evidence.json",
                              f"papers/{paper_id}/statistical-reporting-map.json",
                              f"papers/{paper_id}/failed-study-reporting.json"}
            for sealed in (control.get("confirmation"), control.get("retirement")):
                if sealed:
                    relative_paths.update(sealed.get("files", {}))
            frozen = child / "papers" / paper_id / "preregistration.json"
            rehydratable = {}
            if frozen.is_file():
                for item in read(frozen).get("files", []):
                    if excluded(f"{control['scope_root']}/{item['path']}"):
                        # Raw/private inputs are deliberately absent from cloud
                        # checkpoints. Bind their approved digests, not transient
                        # download presence; checked_child/G4 verifies bytes before
                        # scientific use. Never re-download data just to hash G5.
                        rehydratable[item["path"]] = item["sha256"]
                    else:
                        relative_paths.add(item["path"])
            files = {}
            for relative in sorted(relative_paths):
                target = path_in(child, relative, exists=False)
                files[relative] = sha(target) if target.is_file() else None
            exports = {}
            for item in control.get("parent_exports", []):
                target = path_in(project, item["target"], exists=False)
                exports[item["target"]] = sha(target) if target.is_file() else None
            scopes.append({"path": control_path.relative_to(project).as_posix(), "sha256": sha(control_path),
                           "scope_root": control["scope_root"], "files": files, "rehydratable_inputs": rehydratable,
                           "parent_exports": exports})
    return {"scopes": scopes, "implementation_sha256": sha(Path(__file__))} if scopes else None


def checked_child(project, control):
    child = path_in(project, control["scope_root"], exists=False)
    need(child.is_dir(), "approved supplemental study is missing")
    for item in control["proposal"].get("imports", []):
        source = path_in(project, item["source"])
        target = path_in(child, item["target"], exists=False)
        need(sha(source) == item["sha256"], "authorized supplemental source changed")
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        need(sha(target) == item["sha256"], "supplemental import changed")
    need(sha(child / "state/run.json") == control["child_state_sha256"], "supplemental state changed outside its protected approval")
    state = read(child / "state/run.json")
    need(state.get("approvals") == [control["approval"]], "supplemental G3 approval changed")
    paper = control["paper_id"]
    frozen = project / "papers" / paper / "preregistration.json"
    need(sha(frozen) == control["proposal"]["original_preregistration_sha256"] and sha(project / "experiments/plan.json") == control["proposal"]["original_plan_sha256"], "parent protocol changed during supplemental work")
    runner.approved_plan(child, child / "experiments/plan.json", child / "experiments/budget.json")
    return child


def all_compute_cost(project):
    total = 0.0
    paths = [project / "experiments/registry.jsonl", *(project / PREFIX).glob("P[0-9][0-9]/R[0-9][0-9][0-9]/s[0-9][0-9][0-9]/experiments/registry.jsonl")]
    for path in paths:
        if not path.is_file():
            continue
        # Invalid or non-finite ledger entries must never release budget.
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            value = row["estimated_cost_usd"]
            need(type(value) in (float, int) and math.isfinite(value) and value >= 0, "invalid supplemental cost ledger")
            total += value
    return total


def resume(project, paper_id):
    cloud()
    manifest, _ = current(project, paper_id)
    candidates = controls(project, paper_id, manifest["round_id"])
    if not candidates:
        return {"status": "awaiting_separate_protocol_approval", "executed": False}
    for _, control in candidates:
        child = checked_child(project, control)
        if control.get("retirement"):
            for relative, digest in control["retirement"]["files"].items():
                need(sha(path_in(child, relative)) == digest, "retired failed scope changed")
            continue
        plan = read(child / "experiments/plan.json")
        registry = quality._registry(child)
        for entry in registry:
            need(read(child / "experiments/runs" / entry["attempt_id"] / "run.json") == entry, "supplemental registry differs from executor receipt")
            if entry["status"] != "succeeded":
                return {"status": "inspection_required", "executed": False, "attempt_id": entry["attempt_id"]}
            for output in entry["outputs"]:
                need(sha(path_in(child, output["path"])) == output["sha256"], "supplemental output changed")
        completed = {r["run_id"] for r in registry}
        pending = [r for r in plan["runs"] if r["run_id"] not in completed]
        if not pending:
            from scripts.experiment_evidence import refresh
            refresh(child)
            continue
        cap = read(project / "intake/constraints.json")["cloud_compute_budget_usd"]
        need(all_compute_cost(project) + pending[0]["estimated_cost_usd"] <= cap, "aggregate parent/supplemental compute budget exhausted")
        result = runner.execute(child.name, [pending[0]["run_id"]], project_root=child)[0]
        return {"status": "executed" if result["status"] == "succeeded" else "inspection_required", "executed": True,
                "attempt_id": result["attempt_id"], "scope": control["scope_root"]}
    return {"status": "awaiting_scientific_confirmation", "executed": False}


def prepare_confirmation(project, paper_id, actor):
    cloud()
    value, child, control_path = candidate(project, paper_id)
    control = read(control_path)
    need(control.get("proposal") == value, "approved supplemental proposal changed")
    checked_child(project, control)
    errors = quality.validate_g4_quality(child, require_confirmation=False)
    from scripts import results_validation
    registry = quality._registry(child)
    errors.extend(results_validation.validate_registry(child, read(child / "experiments/plan.json"), registry))
    errors.extend(results_validation.validate_claim_evidence(child, child / "claims/claim-evidence.csv", registry))
    need(not errors, "; ".join(errors))
    if study_routes.route(child, paper_id) == "empirical":
        payload = quality.create_reproduction_confirmation(child, paper_id, actor)
        target = child / "papers" / paper_id / "reproduction-confirmation.json"
    else:
        payload = study_routes.create_confirmation(child, paper_id, actor)
        target = child / "papers" / paper_id / study_routes.CONFIRMATION
    return child, control_path, control, target, payload


def confirm(project, paper_id, actor, review_sha256, run_id):
    child, control_path, control, target, payload = prepare_confirmation(project, paper_id, actor)
    payload.update(source_run_id=run_id, cloud_review_sha256=review_sha256)
    write(target, payload)
    bound = {p.relative_to(child).as_posix(): sha(p) for p in child.rglob("*") if p.is_file()
             and (p.relative_to(child).parts[0] in {"claims", "results", "experiments"} or p.name in {"experiment-evidence.json", "baseline-reproduction.json", "clean-room-reproduction.json", "reproduction-confirmation.json", study_routes.CONFIRMATION})}
    control["confirmation"] = {"actor": actor, "source_run_id": run_id, "cloud_review_sha256": review_sha256, "files": bound,
                               "scientific_completion_verified": False}
    sources = [child / "papers" / paper_id / "experiment-evidence.json"]
    if study_routes.route(child, paper_id) != "empirical":
        sources.extend((child / "papers" / paper_id / "supplement/study-results").glob("*.json"))
    exports = []
    for source in sources:
        target = project / "papers" / paper_id / "supplement/reviewer-experiments" / control["round_id"] / control["scope_id"] / source.name
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, target)
        exports.append({"source": source.relative_to(child).as_posix(), "target": target.relative_to(project).as_posix(), "sha256": sha(target)})
    control["parent_exports"] = exports
    write(control_path, control)
    record(project, [control_path, *[project / e["target"] for e in exports]], "scripts/supplemental_experiments.py")
    record(child, [child / "papers" / paper_id / ("reproduction-confirmation.json" if study_routes.route(child, paper_id) == "empirical" else study_routes.CONFIRMATION)], "scripts/supplemental_experiments.py")
    return control["confirmation"]


def prepare_retirement(project, paper_id):
    cloud()
    value, _, control_path = candidate(project, paper_id)
    control = read(control_path)
    need(control.get("proposal") == value and not control.get("confirmation") and not control.get("retirement"), "select an unconfirmed, unretired approved scope")
    child = checked_child(project, control)
    registry = quality._registry(child)
    need(any(r.get("status") in {"failed", "timed_out"} for r in registry), "retirement requires an actual failed executor attempt")
    runs = {run["run_id"]: run for run in read(child / "experiments/plan.json")["runs"]}
    for row in registry:
        need(row.get("run_id") in runs and row.get("paper_id") == paper_id
             and row.get("approved_plan_sha256") == sha(child / "experiments/plan.json"), "failed attempt must belong to this approved scope and paper")
        need(read(child / "experiments/runs" / row["attempt_id"] / "run.json") == row, "failed registry needs its exact executor receipt")
    files = {p.relative_to(child).as_posix(): sha(p) for p in (child / "experiments").rglob("*") if p.is_file()}
    return child, control_path, control, files


def retire(project, paper_id, actor, review_sha256, run_id, note):
    child, control_path, control, files = prepare_retirement(project, paper_id)
    control["retirement"] = {"actor": actor, "cloud_review_sha256": review_sha256, "source_run_id": run_id, "note": note,
                             "files": files, "failure_statement": "The supplementary experiment did not complete successfully; no result is inferred from it."}
    write(control_path, control); record(project, [control_path], "scripts/supplemental_experiments.py")
    return control["retirement"]


def revision_errors(project, paper_id, *, require_reporting=True):
    try:
        manifest, intake = current(project, paper_id, execution=False)
        values = controls(project, paper_id, manifest["round_id"])
        need(bool(values), "reviewer requests new experiments: a separately approved supplemental protocol and budget are required")
        errors, covered = [], set()
        for _, control in values:
            child = checked_child(project, control)
            if control.get("retirement"):
                retirement = control["retirement"]
                for relative, digest in retirement["files"].items():
                    need(sha(path_in(child, relative)) == digest, "retired failed scope changed")
                if require_reporting:
                    from scripts.ref_verify_adapter import canonical_manuscript
                    from scripts.revision_trace import verify_location
                    mapping = read(child / "papers" / paper_id / "failed-study-reporting.json")
                    need(retirement["failure_statement"] in mapping["excerpt"], "failed supplemental run must be explicitly reported")
                    paper = project / "papers" / paper_id
                    verify_location(paper, canonical_manuscript(paper), json.dumps(mapping["location"]), mapping["excerpt"])
                continue
            covered.update(control["proposal"]["comment_ids"])
            confirmation = control.get("confirmation")
            need(isinstance(confirmation, dict) and confirmation.get("actor"), "supplemental results need fresh named human scientific confirmation")
            for relative, digest in confirmation["files"].items():
                need(sha(path_in(child, relative)) == digest, "confirmed supplemental evidence changed")
            need(bool(control.get("parent_exports")), "supplemental aggregate evidence must be included in the parent submission supplement")
            for exported in control["parent_exports"]:
                need(sha(path_in(child, exported["source"])) == exported["sha256"]
                     and sha(path_in(project, exported["target"])) == exported["sha256"], "supplemental submission evidence changed")
            errors.extend(quality.validate_g4_quality(child))
            if require_reporting:
                if study_routes.route(child, paper_id) != "empirical":
                    errors.extend(study_routes.reporting_audit(child, paper_id, manuscript_project=project)["errors"])
                else:
                    from scripts.statistical_reporting import check_mapping
                    from scripts.experiment_evidence import build_report
                    evidence = build_report(child, paper_id)
                    # Copy only the reporting protocol into a temporary view of
                    # the parent manuscript. Numeric evidence remains computed
                    # from the independently sealed child executor outputs.
                    import tempfile
                    with tempfile.TemporaryDirectory(prefix="supplemental-reporting-") as directory:
                        view = Path(directory)
                        shutil.copytree(project / "papers" / paper_id, view / "papers" / paper_id)
                        shutil.copyfile(child / "papers" / paper_id / "experiment-evidence-plan.json", view / "papers" / paper_id / "experiment-evidence-plan.json")
                        mapping = read(child / "papers" / paper_id / "statistical-reporting-map.json")
                        errors.extend(check_mapping(view, paper_id, evidence, mapping)["errors"])
        requested = {c["comment_id"] for _, control in values for c in control["proposal"]["comment_dispositions"] if c["requires_experiment"]}
        need(not requested or requested <= covered, "supplemental scopes omit reviewer experiment requests")
        return errors
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as exc:
        return [str(exc)]


def prompt_contract():
    return ("Reviewer-requested experiments use a new experiments/supplemental/Pxx/Rxxx/s001 child study, never re-freeze or edit the original G3. "
            "Prepare reviews/reviewer-required-experiment-plan.json with actual comment IDs, prior outcome access, exploratory/prospective-followup status, "
            "original plan/preregistration hashes, imports and a new scope ID. Supply the child's full experiment plan, budget, data quality, power/design "
            "and experiment-evidence plan, or the actual Meta/theory study protocol. supplemental_prepare creates no authority. "
            "The owner separately approves the hash-bound supplemental G3 and confirms actual G4 results. Existing model roles, API budgets, "
            "independent audits and final human G5 remain unchanged; do not claim supplemental results before execution and confirmation.")
