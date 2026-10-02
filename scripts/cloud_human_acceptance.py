"""Cloud-only software acceptance of human controls using synthetic projects.

No real project is opened, no scientific gate is granted for my-phd, and no
model/provider request is made. G3/G4 fixtures test control mechanics, not research.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from scripts import cloud_checkpoint as cp, cloud_human_controls as controls
from scripts import cloud_job, researchctl, research_quality as quality


def request(action: str, **fields) -> dict:
    return {"schema_version": "1.0", "action": action, "project": "human-control-fixture",
            "actor": "Synthetic reviewer - software acceptance only", "allow_paid": False, **fields}


def review(operation: str, **selectors) -> dict:
    return controls.execute(cloud_job.validate_request(
        request("review_dossier", operation=operation, **selectors)), "1")


def decide(operation: str, *, selectors: dict, **decisions) -> dict:
    dossier = review(operation, **selectors)
    if dossier["blockers"]:
        raise RuntimeError("synthetic control fixture blocked: " + json.dumps(dossier["blockers"]))
    job = request(operation, **selectors, **decisions, expected_sha256=dossier["review_sha256"],
                  note="Reviewed this synthetic software fixture; no scientific conclusion is approved.")
    return controls.execute(cloud_job.validate_request(job), "1")


def fixture(root: Path) -> Path:
    project = root / "human-control-fixture"
    researchctl.initialize(SimpleNamespace(project=project.name, paper_count=1, venue="ijssd"))
    constraints = researchctl.read_json(project / "intake/constraints.json")
    constraints.update({
        "status": "ready_for_review", "research_goal": "Test the software control boundary.",
        "researcher_background": "Synthetic acceptance fixture.", "available_skills": ["Python"],
        "time_horizon_years": 3, "weekly_hours": None, "human_review_mode": "on_request",
        "system_execution_hours_per_day": 24, "cash_budget_usd": None, "model_api_budget_cny": 300,
        "cloud_compute_budget_usd": 0, "local_compute": {"gpu": None, "ram_gb": None, "storage_gb": None},
        "ranking_weights": {"funded_position_supply": .25, "job_market_and_salary": .25,
                            "future_growth_potential": .15, "phd_position_competition": .075,
                            "job_market_competition": .075, "background_fit": .1, "application_route_fit": .1},
    })
    researchctl.write_json(project / "intake/constraints.json", constraints)
    state = researchctl.load_state(project.name)
    state["synthetic_acceptance_only"] = True
    researchctl.save_state(project.name, state)
    return project


def set_fixture_stage(project: Path, gate: str) -> None:
    """Fixture setup only: bypassing real science is never a cloud action."""
    state = researchctl.load_state(project.name)
    index = int(gate[1:])
    state.update(stage_index=index, stage=researchctl.STAGES[index]["name"], gate=gate, status="awaiting_work")
    state.pop("ready_gate", None)
    state.pop("ready_artifact_sha256", None)
    researchctl.save_state(project.name, state)


def quality_fixture(project: Path, *, real_power: bool = False) -> None:
    data = project / "data/raw/dataset.csv"
    data.write_text("machine,split,label,value\nA,train,ok,1\nB,train,fault,2\nC,test,ok,3\n", encoding="utf-8")
    manifest = {"dataset_id": "d1", "download": {"sha256": cp.sha(data)}, "provenance": {"transformations": []}}
    (project / "data/datasets.jsonl").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    researchctl.write_json(project / "papers/P01/paper-contract.json",
                           {"paper_id": "P01", "datasets": ["d1"], "hypotheses": [{"id": "H1"}]})
    design = {
        "paper_id": "P01", "design_id": "D1",
        "baselines": [{"id": "B1", "class": "domain_standard", "primary_source_url": "https://example.org/b1"},
                      {"id": "B2", "class": "strong_recent", "primary_source_url": "https://example.org/b2"}],
        "reproduction_plan": {
            "baseline_runs": {"domain_standard": ["base-domain"], "strong_recent": ["base-recent"]},
            "original_run_ids": ["original"], "clean_room_run_ids": ["reproduction"],
            "metric_tolerances": [{"metric": "F1", "absolute_tolerance": .02, "rationale": "Synthetic locked margin."}],
        },
    }
    design_path = project / "papers/P01/experiments/primary.json"
    researchctl.write_json(design_path, design)
    researchctl.write_json(project / "experiments/plan.json", {"status": "ready_for_review", "runs": []})
    researchctl.write_json(project / "experiments/budget.json", {"status": "ready_for_review", "hard_ceiling_usd": 0})
    if real_power:
        power = quality.create_power_report(project, "P01", "ttest_ind", .5, .05, .8, 1.,
                                            "Synthetic effect assumption for software testing only.")
    else:
        power = {"schema_version": "1.0", "paper_id": "P01", "status": "ready_for_review",
                 "human_review_required": True, "generated_by": "statsmodels", "engine_version": "0.15.0",
                 "method": "ttest_ind", "effect_size": .5, "effect_size_basis": "Synthetic validation fixture only.",
                 "alpha": .05, "target_power": .8, "required_sample_size": {"group_1": 64, "group_2": 64},
                 "bound_files": [{"path": p.relative_to(project).as_posix(), "sha256": cp.sha(p)}
                                 for p in (project / "papers/P01/paper-contract.json", design_path)]}
    researchctl.write_json(project / "papers/P01/power-analysis.json", power)
    report = quality.create_data_quality_report(project, "d1", "data/raw/dataset.csv", actor="Synthetic fixture")
    researchctl.write_json(project / "data/quality/d1.json", report)


def reproduction_fixture(project: Path) -> None:
    """Explicitly synthetic receipts; real executor acceptance is a separate job."""
    evidence = project / "experiments/metrics.json"
    evidence.write_text('{"metric": 0.8, "synthetic": true}\n', encoding="utf-8")
    outputs = [{"path": evidence.relative_to(project).as_posix(), "sha256": cp.sha(evidence)}]
    registry = []
    for run, attempt in (("base-domain", "a1"), ("base-recent", "a2"), ("original", "a3"), ("reproduction", "b1")):
        clean = attempt == "b1"
        registry.append({
            "run_id": run, "attempt_id": attempt, "paper_id": "P01", "status": "succeeded",
            "cwd": "env-b" if clean else "env-a", "git_commit": "a" * 40,
            "runtime": {"python": "3.12", "platform": "linux-b" if clean else "linux-a"},
            "executor_isolation": {
                "kind": "container" if clean else "host", "instance_id": attempt,
                "isolated_executor": clean, "network_disabled": clean, "read_only_root": clean,
                "fingerprint": ("e" if clean else "c") * 64,
                **({"image_digest": "d" * 64} if clean else {}),
            },
            "outputs": outputs, "synthetic_acceptance_only": True,
        })
    (project / "experiments/registry.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in registry), encoding="utf-8")
    baseline = {
        "schema_version": "1.0", "paper_id": "P01", "status": "pass", "human_review_required": True,
        "baselines": [
            {"baseline_id": b, "class": cls, "metric": "F1", "reference_source_url": "https://example.org/" + b.lower(),
             "reference_value": reference, "observed_value": reference - .01, "absolute_tolerance": .02,
             "comparable_protocol": True, "within_tolerance": True, "run_ids": [run], "attempt_ids": [attempt],
             "evidence_files": outputs, "comparison_notes": "Synthetic fixture only."}
            for b, cls, reference, run, attempt in (("B1", "domain_standard", .8, "base-domain", "a1"),
                                                   ("B2", "strong_recent", .82, "base-recent", "a2"))
        ],
    }
    clean = {
        "schema_version": "1.0", "paper_id": "P01", "status": "pass", "human_review_required": True,
        "independent_operator": "Synthetic independent fixture",
        "original_run_ids": ["original"], "reproduction_run_ids": ["reproduction"],
        "original_attempt_ids": ["a3"], "reproduction_attempt_ids": ["b1"],
        "isolation": {"isolated_executor": True, "reproduction_kind": "container",
                      "original_isolation_ids": ["a3"], "reproduction_isolation_ids": ["b1"],
                      "original_environment_digest": quality.registry_environment_digest(registry, ["a3"]),
                      "reproduction_environment_digest": quality.registry_environment_digest(registry, ["b1"]),
                      "source_commit": "a" * 40},
        "metric_comparisons": [{"metric": "F1", "original_value": .8, "reproduction_value": .79,
                                "absolute_tolerance": .02, "within_tolerance": True}],
        "evidence_files": outputs,
    }
    researchctl.write_json(project / "papers/P01/baseline-reproduction.json", baseline)
    researchctl.write_json(project / "papers/P01/clean-room-reproduction.json", clean)


def run(directory: Path, *, real_power: bool = True) -> dict:
    directory = directory.resolve()
    old_root = researchctl.PROJECTS_ROOT
    researchctl.PROJECTS_ROOT = directory / "projects"
    try:
        project = fixture(researchctl.PROJECTS_ROOT)
        spend_before = cp.sha(project / "state/model-spend-control.json")
        intake = cp.sha(project / "intake/constraints.json")
        if researchctl.gate_errors(project.name, "G0"):
            raise RuntimeError("G0 fixture must pass the real intake validator")
        decide("ready", selectors={"gate": "G0"})
        decide("approve", selectors={"gate": "G0"})
        decide("advance", selectors={"gate": "G0"})
        if researchctl.load_state(project.name)["gate"] != "G1" or not review("ready", gate="G1")["blockers"]:
            raise RuntimeError("missing scientific evidence must still block G1")
        set_fixture_stage(project, "G3")
        quality_fixture(project, real_power=real_power)
        decide("confirm_data_quality", selectors={"dataset_id": "d1"})
        decide("freeze_preregistration", selectors={"paper_id": "all"})
        prereg = researchctl.read_json(project / "papers/P01/preregistration.json")
        if quality.validate_preregistration(prereg, "P01", project):
            raise RuntimeError("preregistration fixture failed its original validator")
        set_fixture_stage(project, "G4")
        reproduction_fixture(project)
        decide("confirm_reproduction", selectors={"paper_id": "P01"})
        confirmation = researchctl.read_json(project / "papers/P01/reproduction-confirmation.json")
        if quality.validate_reproduction_confirmation(confirmation, "P01", project):
            raise RuntimeError("reproduction fixture failed its original validator")
        if spend_before != cp.sha(project / "state/model-spend-control.json") or intake != cp.sha(project / "intake/constraints.json"):
            raise RuntimeError("human controls changed spending authority or intake")
        state = researchctl.load_state(project.name)
        if state["approved_gates"] != ["G0"]:
            raise RuntimeError("evidence confirmations must not grant G3/G4 approval")
        result = {
            "schema_version": "1.0", "status": "pass", "scope": "synthetic software controls only",
            "scientific_completion_verified": False, "paid_provider_calls": 0,
            "checks": ["real G0 ready/approve/advance", "incomplete G1 still blocked",
                       "named data quality confirmation", "all-paper preregistration freeze",
                       "named reproduction confirmation", "spending and intake unchanged",
                       "no G3/G4 scientific approval"],
            "real_statsmodels_power": real_power,
            "decision_log_sha256": cp.sha(project / controls.AUDIT),
            "spend_control_sha256": spend_before,
        }
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "acceptance.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return result
    finally:
        researchctl.PROJECTS_ROOT = old_root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    run(parser.parse_args().directory)


if __name__ == "__main__":
    main()
