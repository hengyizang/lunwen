"""Cloud software acceptance on explicitly synthetic studies, never real research."""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch

from scripts import cloud_checkpoint, cloud_human_controls, experiment_evidence, experiment_runner
from scripts import research_identity, research_quality, researchctl, study_environment, study_routes
from scripts.research_artifacts import read, sha, write


def make_study(project, kind, *, provision=False, analysis_phase="confirmatory"):
    project.mkdir(parents=True, exist_ok=True)
    paper_id = "P01"
    paper = project / "papers" / paper_id
    paper.mkdir(parents=True, exist_ok=True)
    write(project / "state/run.json", {"schema_version": "2.0", "project": project.name, "stage_index": 3,
        "stage": "experiment-design", "gate": "G3", "status": "awaiting_work", "active_paper": paper_id,
        "paper_count": 1, "paper_statuses": {paper_id: "active"}, "approved_gates": [], "approvals": [], "history": []})
    (project / "data").mkdir(exist_ok=True)
    (project / "data/datasets.jsonl").write_text("", encoding="utf-8")
    write(paper / "paper-contract.json", {"paper_id": paper_id, "study_route": kind, "datasets": [],
        "independence": {"unique_claim_ids": ["C1"]}, "planned_experiments": {"design_ids": ["study-protocol"]}})
    identity = research_identity.template(paper_id)
    identity.update(research_kind="secondary_quantitative" if kind == "meta_analysis" else "primary",
        design_family="meta-analysis" if kind == "meta_analysis" else "theoretical",
        methods=["meta_analysis"] if kind == "meta_analysis" else ["formal_proof"], claim_ids=["C1"],
        reporting_description="Synthetic Meta analysis software fixture." if kind == "meta_analysis" else "Synthetic formal theory software fixture.",
        secondary_protocol={} if kind == "meta_analysis" else None)
    write(paper / "research-identity.json", identity)
    references = []
    for i in range(3):
        path = project / f"evidence/closest-{i}.txt"
        path.parent.mkdir(exist_ok=True)
        quote = f"Synthetic closest-work comparison {i}; no actual scientific source is asserted."
        path.write_text(quote + "\n", encoding="utf-8")
        references.append({"path": path.relative_to(project).as_posix(), "sha256": sha(path), "start_line": 1, "end_line": 1, "quote": quote})
    protocol = {"schema_version": "1.0", "paper_id": paper_id, "status": "ready_for_review", "route": kind,
        "question": "Synthetic software acceptance; no doctoral finding is claimed.", "claim_ids": ["C1"],
        "methodological_review": "Synthetic fixture isolates execution, statistics and proof obligations.",
        "closest_work_comparison": references, "limitations": ["Synthetic software validation only."],
        "replication_plan": "Re-run the exact frozen inputs in a separate no-network read-only Docker instance.",
        "replication_tolerance": 1e-10, "deviation_policy": "Retain failures, null outcomes and original frozen files.",
        "runtime_path": "analysis/runtime/P01/runtime.py", "execution_runs": ["study-original", "study-replay"],
        "outputs": {"study-original": "results/original.json", "study-replay": "results/replay.json"}}
    if kind == "meta_analysis":
        works = [{"id": f"S{i}"} for i in range(1, 6)]
        raw, normalized = project / "evidence/raw-search.json", project / "evidence/normalized-search.json"
        write(raw, {"synthetic": True, "works": works}); write(normalized, {"works": works})
        ledger = {"receipt_id": "synthetic-search", "status": "success", "raw_response_path": "evidence/raw-search.json",
                  "response_sha256": sha(raw), "normalized_results_path": "evidence/normalized-search.json", "normalized_results_sha256": sha(normalized)}
        (project / "evidence/literature-api-ledger.jsonl").write_text(json.dumps(ledger) + "\n", encoding="utf-8")
        write(project / "evidence/selection.json", {"search_receipt_ids": ["synthetic-search"], "records": [
            {"work_id": f"S{i}", "decision": "include" if i < 5 else "exclude", "reason": "Synthetic eligibility decision retained for software testing."} for i in range(1, 6)]})
        records = []
        for i, (effect, variance) in enumerate(zip([.1, .2, -.1, .3], [.02, .03, .02, .04]), 1):
            path = project / f"evidence/study-{i}.txt"
            quote = f"Synthetic study {i}: effect {effect}; sampling variance {variance}; no real population."
            path.write_text(quote + "\n", encoding="utf-8")
            records.append({"study_id": f"S{i}", "cohort_id": f"cohort-{i}", "outcome_id": "primary", "effect_measure": "mean_difference",
                "effect": effect, "variance": variance, "risk_of_bias": "high" if i == 4 else "low",
                "bias_rationale": "Synthetic bias category used to test sensitivity reporting.", "license_or_research_rights": "Repository-authored synthetic numerical fixture.",
                "source": {"path": path.relative_to(project).as_posix(), "sha256": sha(path), "start_line": 1, "end_line": 1, "quote": quote},
                "independent_extractions": [{"reviewer": "Synthetic extractor A", "effect": effect, "variance": variance},
                                            {"reviewer": "Synthetic extractor B", "effect": effect, "variance": variance}]})
        write(project / "evidence/extraction.json", {"records": records})
        protocol.update(selection_file="evidence/selection.json", extraction_file="evidence/extraction.json", outcomes=[{
            "id": "primary", "claim_ids": ["C1"], "estimand": "Mean synthetic study-level difference.",
            "population": "Synthetic studies without a real scientific population.", "comparability": "All effects use the same synthetic linear scale.",
            "precision_rationale": "Four studies exercise uncertainty; no claim of adequate scientific precision.",
            "effect_measure": "mean_difference", "direction": "greater", "minimum_effect": .05,
            "analysis_phase": analysis_phase, "family": "primary-family", "alpha": .05}])
    else:
        source = project / "analysis/proof.lean"
        source.parent.mkdir(exist_ok=True)
        source.write_text("import Std\n"
            "theorem add_zero_main (n : Nat) : n + 0 = n := by simp\n"
            "theorem natural_witness : ∃ n : Nat, n = 0 := ⟨0, rfl⟩\n"
            "theorem zero_add_scope (n : Nat) : 0 + n = n := by simp\n", encoding="utf-8")
        declarations = [("main", "add_zero_main", "∀ n : Nat, n + 0 = n", "For every natural number n, adding zero on the right preserves n."),
                        ("assumption_witness", "natural_witness", "∃ n : Nat, n = 0", "There exists a natural number equal to zero, so the domain is inhabited."),
                        ("scope_check", "zero_add_scope", "∀ n : Nat, 0 + n = n", "For every natural number n, adding zero on the left also preserves n.")]
        protocol.update(proof_timeout_seconds=120, theorems=[{"id": role, "claim_ids": ["C1"], "role": role,
            "declaration": declaration, "formal_type": type_, "statement": statement, "assumptions": "All variables range over natural numbers.",
            "scope": "Natural-number addition only; this fixture claims no original theorem.", "proof_strategy": "Use the trusted standard library and Lean kernel.",
            "comparison_to_closest_result": "Known elementary equalities used exclusively as software acceptance.",
            "source": "analysis/proof.lean", "sha256": sha(source), "depends_on": []} for role, declaration, type_, statement in declarations])
    write(paper / study_routes.PROTOCOL, protocol)
    runtime_source = Path(study_routes.__file__).parent / ("meta_analysis_runtime.py" if kind == "meta_analysis" else "theory_verification_runtime.py")
    runtime = project / protocol["runtime_path"]
    runtime.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(runtime_source, runtime)
    write(paper / study_routes.IDENTITY_LOCK, study_routes.identity_projection(project, paper_id))
    sources = [p for p in project.rglob("*") if p.is_file() and p.relative_to(project).parts[0] in {"evidence", "analysis"}]
    sources += [paper / study_routes.PROTOCOL, paper / study_routes.IDENTITY_LOCK, paper / "paper-contract.json"]
    from scripts.live_acceptance import DEFAULT_IMAGE
    fake_binding = {"profile": kind, "definition_sha256": study_environment.definition(kind), "base_image": DEFAULT_IMAGE, "environment_sha256": "0" * 64}
    runs = []
    for run_id in protocol["execution_runs"]:
        args = ["python3", protocol["runtime_path"], f"papers/{paper_id}/{study_routes.PROTOCOL}"]
        if kind == "meta_analysis":
            args.append(protocol["extraction_file"])
        args.append(protocol["outputs"][run_id])
        runs.append({"run_id": run_id, "paper_id": paper_id, "argv": args, "cwd": ".", "seed": 0, "timeout_seconds": 300,
            "estimated_cost_usd": 0, "isolation": {"kind": "container", "engine": "docker", "image": DEFAULT_IMAGE}, "runtime": fake_binding,
            "inputs": [{"path": p.relative_to(project).as_posix(), "sha256": sha(p)} for p in sources], "expected_outputs": [protocol["outputs"][run_id]]})
    write(project / "experiments/plan.json", {"schema_version": "1.0", "status": "ready_for_review", "runs": runs})
    write(project / "experiments/budget.json", {"schema_version": "1.0", "status": "ready_for_review", "hard_ceiling_usd": 0})
    if provision:
        study_routes.prepare_runtime(project, paper_id)
    else:
        with patch("scripts.study_environment.prepare", return_value=(fake_binding, project)):
            study_routes.prepare_runtime(project, paper_id)
    return protocol


def freeze(project):
    paper = "P01"
    frozen = research_quality.create_preregistration(project, paper, "Synthetic CI reviewer; not project approval")
    prereg = project / "papers/P01/preregistration.json"; write(prereg, frozen)
    state = read(project / "state/run.json")
    state.update(stage_index=4, stage="experiment-execution", gate="G4", status="awaiting_work", approved_gates=["G3"], approvals=[{
        "gate": "G3", "actor": "Synthetic CI reviewer; not project approval", "experiment_plan_sha256": sha(project / "experiments/plan.json"),
        "experiment_budget_sha256": sha(project / "experiments/budget.json"), "frozen_protocol_sha256": {"papers/P01/preregistration.json": sha(prereg)}}])
    write(project / "state/run.json", state)


def claim_matrix(project, report):
    path = project / "claims/claim-evidence.csv"; path.parent.mkdir(parents=True, exist_ok=True)
    from scripts.results_validation import CLAIM_COLUMNS
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted(CLAIM_COLUMNS | {"comparison_ids"})); writer.writeheader()
        writer.writerow({"claim_id": "C1", "paper_id": "P01", "claim": "Synthetic software result; not a scientific contribution.",
            "evidence_ids": "synthetic", "analysis_ids": "study-original;study-replay",
            "comparison_ids": ";".join(c["comparison_id"] for c in report["comparisons"]), "support": "not_supported",
            "uncertainty": "No real study, originality or publication claim.", "status": "synthetic_software_acceptance"})


def reporting_fixture(project, report, *, manuscript_project=None, label="Original"):
    manuscript_project = manuscript_project or project
    manuscript = manuscript_project / "papers/P01/manuscript/main.tex"
    manuscript.parent.mkdir(parents=True, exist_ok=True)
    lines = ["\\documentclass{article}", "\\begin{document}", "\\section{Results}"]
    if manuscript.is_file():
        lines = manuscript.read_text(encoding="utf-8").splitlines()
        if lines and lines[-1] == "\\end{document}":
            lines.pop()
    items = []
    for result in report["comparisons"]:
        row = {"result_id": result["comparison_id"], "interpretation": "Synthetic fixture only; no scientific contribution is asserted.",
               "uncertainty": "Interpretation is limited to synthetic studies or the exact formal assumptions."}
        if report["route"] == "meta_analysis":
            actual = result["statistics"]
            row.update(analysis_phase=actual["analysis_phase"], decision=actual["decision"])
            numbers = {**{k: actual["summary"][k] for k in ("k", "estimate", "ci_low", "ci_high", "tau_squared", "i_squared")}, "p_adjusted": actual["p_adjusted"]}
            row["values"] = {k: f"{v:.6f}" for k, v in numbers.items()}
            excerpt = label + " " + actual["analysis_phase"] + " synthetic Meta result " + result["comparison_id"] + ": " + ", ".join(k + "=" + v for k, v in row["values"].items()) + "."
        else:
            excerpt = label + ": " + result["proof"]["natural_language_statement"]
            row["formal_type"] = result["proof"]["checked_type"]
        lines.append(excerpt); row["excerpt"] = excerpt; row["line"] = len(lines); items.append(row)
    lines.append("\\end{document}"); manuscript.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for row in items:
        row["location"] = {"kind": "source_lines", "path": "manuscript/main.tex", "sha256": sha(manuscript), "start_line": row.pop("line"), "end_line": len(lines)-1}
    write(project / "papers/P01/statistical-reporting-map.json", {"schema_version": "1.0", "items": items})
    return manuscript


def supplemental_acceptance(parent, *, execute=True):
    from scripts import reviewer_rounds, supplemental_experiments as supplemental
    paper = "P01"
    manuscript = parent / "papers/P01/manuscript/main.tex"
    if not manuscript.is_file():
        manuscript.parent.mkdir(parents=True, exist_ok=True)
        manuscript.write_text("\\documentclass{article}\n\\begin{document}\nSynthetic software fixture only.\n\\end{document}\n", encoding="utf-8")
    write(parent / "intake/constraints.json", {"execution_mode": "cloud_only", "cloud_compute_budget_usd": 0})
    source = parent / "evidence/reviewer-intake/P01/reviewer.txt"; source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("Reviewer 1\nPlease conduct a separately planned sensitivity experiment.\n", encoding="utf-8")
    receipt = source.with_name("submission.txt"); receipt.write_text("Synthetic submission FIXTURE-1 received.\n", encoding="utf-8")
    intake = {"schema_version": "1.0", "paper_id": paper, "review_type": "external", "journal": "Synthetic Fixture Journal",
        "manuscript_id": "FIXTURE-1", "submitted_at": "2026-10-01T00:00:00Z", "needs_new_experiments": True,
        "submission_receipt": {"path": receipt.relative_to(parent).as_posix(), "sha256": sha(receipt), "locator": "line 1", "quote": "Synthetic submission FIXTURE-1 received."},
        "reviewer_source": {"path": source.relative_to(parent).as_posix(), "sha256": sha(source)}, "comments": [
            {"comment_id": "R1-C1", "reviewer_id": "Reviewer 1", "comment": "Please conduct a separately planned sensitivity experiment.", "source_location": {"start_line": 2, "end_line": 2}}]}
    intake_path = source.with_name("intake.json"); write(intake_path, intake)
    state = read(parent / "state/run.json")
    state.update(stage_index=6, stage="submission-ready", gate=None, status="submission_ready", approved_gates=["G3", "G4", "G5:P01"], paper_statuses={paper: "submission_ready"})
    write(parent / "state/run.json", state)
    original = {path.relative_to(parent).as_posix(): path.read_bytes() for path in research_quality._preregistration_inputs(parent, paper)}
    original["papers/P01/preregistration.json"] = (parent / "papers/P01/preregistration.json").read_bytes()
    with patch.object(researchctl, "PROJECTS_ROOT", parent.parent):
        state["approvals"].append({"gate": "G5", "paper_id": paper, "actor": "Synthetic CI reviewer", "paper_artifact_sha256": researchctl.paper_artifact_hash(parent.name, paper)})
        write(parent / "state/run.json", state)
        reviewer_rounds.start_revision(parent, paper, intake_path.relative_to(parent).as_posix(), "Synthetic CI reviewer", "a" * 64, "123")
        proposal = {"schema_version": "1.0", "paper_id": paper, "round_id": "R001", "scope_id": "s001", "comment_ids": ["R1-C1"],
            "comment_dispositions": [{"comment_id": "R1-C1", "requires_experiment": True, "rationale": "The synthetic reviewer explicitly requests an additional experiment."}],
            "analysis_phase": "exploratory", "prior_outcomes_seen": True, "rationale": "Synthetic reviewer follow-up exercises the separate approval/execution path.",
            "outcome_access_statement": "The synthetic original outcome was already inspected; no retrospective confirmation is claimed.",
            "scope_and_claim_limits": "Supplemental software fixture only, not an actual requested scientific study.", "imports": [],
            "original_plan_sha256": sha(parent / "experiments/plan.json"), "original_preregistration_sha256": sha(parent / "papers/P01/preregistration.json")}
        write(parent / "papers/P01" / supplemental.PROPOSAL, proposal)
        child = parent / "experiments/supplemental/P01/R001/s001"
        make_study(child, "meta_analysis", provision=execute, analysis_phase="exploratory")
        supplemental.prepare(parent, paper)
        if not execute:
            return {"child": child, "proposal": proposal}
        before = supplemental.resume(parent, paper)
        if before["executed"]:
            raise AssertionError("unapproved reviewer request executed")
        value = {"schema_version": "1.0", "action": "review_dossier", "operation": "approve_supplemental", "project": parent.name,
                 "actor": "Synthetic CI reviewer", "allow_paid": False, "paper_id": paper}
        dossier = cloud_human_controls.dossier(value)
        if dossier["blockers"]:
            raise AssertionError(dossier["blockers"])
        value.update(action="approve_supplemental", expected_sha256=dossier["review_sha256"], note="Synthetic supplemental protocol and zero-cost budget reviewed."); value.pop("operation")
        cloud_human_controls.execute(value, "124")
        executions = [supplemental.resume(parent, paper) for _ in range(3)]
        report = study_routes.build_report(child, paper)
        if report["status"] != "complete":
            raise AssertionError(report)
        claim_matrix(child, report)
        value = {"schema_version": "1.0", "action": "review_dossier", "operation": "confirm_supplemental", "project": parent.name,
                 "actor": "Synthetic CI reviewer", "allow_paid": False, "paper_id": paper}
        dossier = cloud_human_controls.dossier(value)
        if dossier["blockers"]:
            raise AssertionError(dossier["blockers"])
        value.update(action="confirm_supplemental", expected_sha256=dossier["review_sha256"], note="Synthetic actual results and isolated replay reviewed."); value.pop("operation")
        cloud_human_controls.execute(value, "125")
        reporting_fixture(child, report, manuscript_project=parent, label="Supplemental")
        errors = supplemental.revision_errors(parent, paper)
        if errors:
            raise AssertionError(errors)
        binding = supplemental.review_binding(parent, paper, ["R001"])
        if len(binding["scopes"]) != 1 or not binding["scopes"][0]["parent_exports"]:
            raise AssertionError("actual supplemental results are missing from the final review binding")
        parent_state = parent / "state/run.json"
        original_state = parent_state.read_bytes()
        for status in ("awaiting_approval", "approved"):
            state = read(parent_state); state["status"] = status; write(parent_state, state)
            if supplemental.revision_errors(parent, paper) or supplemental.review_binding(parent, paper, ["R001"]) != binding:
                raise AssertionError("final G5 status changed the supplemental scientific review")
        parent_state.write_bytes(original_state)
        for relative, content in original.items():
            if (parent / relative).read_bytes() != content:
                raise AssertionError("original G3 input was rewritten: " + relative)
    return {"actual_separate_scope_execution": True, "unapproved_execution_blocked": True,
            "original_g3_bytes_unchanged": True, "owner_approval_and_confirmation_functions_exercised": True,
            "supplemental_evidence_binding_verified": True,
            "executions": executions, "paid_model_calls": 0, "scientific_completion_verified": False}


def reject_false_proof(directory):
    project = directory / "projects/false-proof"
    make_study(project, "theory", provision=True)
    source = project / "analysis/proof.lean"
    source.write_text(source.read_text(encoding="utf-8").replace("n + 0 = n := by simp", "n + 1 = n := by rfl"), encoding="utf-8")
    path = project / "papers/P01/study-protocol.json"; value = read(path)
    value["theorems"][0]["formal_type"] = "∀ n : Nat, n + 1 = n"
    write(path, value); study_routes.prepare_runtime(project, "P01"); freeze(project)
    attempts = experiment_runner.execute(project.name, ["study-original"], project_root=project)
    if attempts[0]["status"] != "failed":
        raise AssertionError("false theorem passed Lean kernel checking")
    from scripts.cloud_research_steps import resume_experiments
    before = (project / "experiments/registry.jsonl").read_bytes()
    resumed = resume_experiments(project)
    if not resumed["blockers"] or before != (project / "experiments/registry.jsonl").read_bytes():
        raise AssertionError("failed proof was retried or omitted")
    return {"false_theorem_rejected_by_real_kernel": True, "failed_attempt_preserved_without_retry": True,
            "attempt_id": attempts[0]["attempt_id"], "scientific_completion_verified": False}


def accept(directory):
    os.environ["DR_OS_CLOUD_EXECUTOR"] = "1"
    directory.mkdir(parents=True, exist_ok=True)
    cases = []
    for kind, slug in (("meta_analysis", "meta-demo"), ("theory", "theory-demo")):
        project = directory / "projects" / slug
        make_study(project, kind, provision=True)
        if study_routes.plan_errors(project, "P01"):
            raise AssertionError(study_routes.plan_errors(project, "P01"))
        freeze(project)
        attempts = experiment_runner.execute(slug, project_root=project)
        if any(a["status"] != "succeeded" for a in attempts):
            raise AssertionError(json.dumps(attempts, indent=2))
        experiment_evidence.refresh(project)
        report = study_routes.build_report(project, "P01")
        if report["status"] != "complete":
            raise AssertionError(report)
        claim_matrix(project, report)
        with patch.object(researchctl, "PROJECTS_ROOT", project.parent):
            value = {"schema_version": "1.0", "action": "review_dossier", "operation": "confirm_study_validation", "project": slug,
                     "actor": "Synthetic CI reviewer", "allow_paid": False, "paper_id": "P01"}
            dossier = cloud_human_controls.dossier(value)
            if dossier["blockers"]:
                raise AssertionError(dossier["blockers"])
            value.update(action="confirm_study_validation", expected_sha256=dossier["review_sha256"], note="Synthetic fixture reviewed for software acceptance only.")
            value.pop("operation")
            cloud_human_controls.execute(value, "123")
        if research_quality.validate_g4_quality(project):
            raise AssertionError(research_quality.validate_g4_quality(project))
        reporting_fixture(project, report)
        if study_routes.reporting_audit(project, "P01")["errors"]:
            raise AssertionError(study_routes.reporting_audit(project, "P01"))
        # Exact checkpoint/restore must retain proof sources and trusted runtime.
        inventory = cloud_checkpoint.inventory(project)
        if kind == "theory" and not any(r["path"] == "analysis/proof.lean" for r in inventory):
            raise AssertionError("Lean sources were omitted from checkpoint")
        cases.append({"route": kind, "attempt_ids": [a["attempt_id"] for a in attempts], "evidence_sha256": sha(project / "papers/P01/experiment-evidence.json"),
                      "actual_isolated_execution": True, "human_control_function_exercised_with_synthetic_identity": True,
                      "scientific_completion_verified": False})
    supplemental = supplemental_acceptance(directory / "projects/meta-demo")
    failed_proof = reject_false_proof(directory)
    result = {"schema_version": "1.0", "status": "passed", "cases": cases, "supplemental": supplemental, "failed_proof": failed_proof, "paid_model_calls": 0,
              "scientific_completion_verified": False, "scope": "Synthetic software acceptance only; no selected real topic or paper is validated."}
    write(directory / "acceptance.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args(); print(json.dumps(accept(args.directory.resolve()), indent=2))


if __name__ == "__main__":
    main()
