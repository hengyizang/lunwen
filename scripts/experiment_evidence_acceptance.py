"""Synthetic component acceptance; never a scientific approval or real dataset.

The seeded G3 receipt exists only inside temporary acceptance fixtures. Production
approvals still require researchctl's complete human G3 gate.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

from scripts import experiment_evidence as evidence, experiment_runner as runner
from scripts import research_quality, researchctl, results_validation
from scripts.live_acceptance import DEFAULT_IMAGE

SEEDS = [11, 22, 33]
CONDITIONS = [
    ("weak", "primary"), ("domain", "primary"), ("recent", "primary"),
    ("remove-component", "ablation"), ("null-control", "negative_control"),
    ("shift", "robustness"), ("noise", "robustness"),
]

CODE = """import csv, os, sys
from pathlib import Path
assert not os.environ.get('UUAPI_API_KEY')
assert not os.environ.get('UUAPI_OPENAI_API_KEY')
assert not os.environ.get('UUAPI_ANTHROPIC_API_KEY')
condition, seed, output = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3])
output.parent.mkdir(parents=True, exist_ok=True)
if condition.startswith('pilot'):
    output.write_text('synthetic pilot diagnostic; no scientific result', encoding='utf-8')
    if condition == 'pilot-fail':
        raise RuntimeError('intentional pilot failure')
    raise SystemExit(0)
with output.open('w', newline='', encoding='utf-8') as handle:
    writer = csv.writer(handle)
    writer.writerow(['unit', 'value'])
    for unit in range(12):
        delta = {
            'proposed': 0.0, 'weak': 2 + .04*unit, 'domain': 1 + .025*unit,
            'recent': -.4 + .01*unit, 'remove-component': .9 + .03*unit,
            'null-control': -.03 + .005*unit, 'shift': .6 + .02*unit,
            'noise': (-1)**unit * .05,
        }[condition]
        if condition != 'proposed':
            delta += .01*(seed//11 - 2) * (-1)**unit
        for repeat in (-1, 1):
            writer.writerow([f'u{unit:02}', 10 + unit - delta + repeat*.01])
"""


def write(path: Path, value: dict) -> None:
    researchctl.write_json(path, value)


def freeze_fixture(project: Path) -> None:
    """Create explicitly synthetic upstream receipts to isolate this component."""
    paths = research_quality._preregistration_inputs(project, "P01")
    for path in paths:
        if not path.is_file():
            write(path, {"synthetic_component_fixture_only": True})
    prereg = project / "papers/P01/preregistration.json"
    write(prereg, {
        "schema_version": "1.0", "paper_id": "P01", "status": "frozen",
        "generated_by": "deterministic_local_control_plane", "confirmatory_lock": True,
        "human_confirmation": True, "frozen_by": "synthetic component fixture, not human approval",
        "frozen_at": "2026-10-02T00:00:00Z", "synthetic_acceptance_only": True,
        "deviation_policy": "Block changed inputs and retain every result.",
        "files": [{"path": p.relative_to(project).as_posix(), "sha256": evidence.sha(p)} for p in paths],
    })
    write(project / "state/run.json", {
        "stage": "experiment-execution", "gate": "G4", "status": "awaiting_work",
        "synthetic_acceptance_only": True, "approvals": [{
            "gate": "G3", "actor": "synthetic component fixture, not project approval",
            "experiment_plan_sha256": evidence.sha(project / "experiments/plan.json"),
            "experiment_budget_sha256": evidence.sha(project / "experiments/budget.json"),
            "frozen_protocol_sha256": {"papers/P01/preregistration.json": evidence.sha(prereg)},
        }],
    })


def fixture(project: Path, *, container: bool = False, fail_pilot: bool = False) -> dict:
    if project.exists():
        raise ValueError("fixture must start in a fresh directory")
    code_path = project / "experiments/code/measure.py"
    code_path.parent.mkdir(parents=True)
    code_path.write_text(CODE, encoding="utf-8")
    isolation = ({"kind": "container", "engine": "docker", "image": DEFAULT_IMAGE}
                 if container else {"kind": "host"})
    executable = "python3" if container else sys.executable
    runs = []
    for condition, seed in [("pilot", 0)] + [
            (condition, seed) for condition in ["proposed"] + [c for c, _ in CONDITIONS] for seed in SEEDS]:
        run_id = f"{condition}-{seed}"
        output = f"results/{run_id}.csv"
        runs.append({
            "run_id": run_id, "paper_id": "P01", "cwd": ".", "seed": seed,
            "argv": [executable, "experiments/code/measure.py",
                     "pilot-fail" if condition == "pilot" and fail_pilot else condition, str(seed), output],
            "timeout_seconds": 60, "estimated_cost_usd": 0, "isolation": isolation,
            "inputs": [{"path": "experiments/code/measure.py", "sha256": evidence.sha(code_path)}],
            "expected_outputs": [output], "depends_on": [] if condition == "pilot" else ["pilot-0"],
        })
    write(project / "experiments/plan.json", {"schema_version": "1.0", "status": "ready_for_review", "runs": runs})
    write(project / "experiments/budget.json", {"status": "ready_for_review", "hard_ceiling_usd": 0})
    write(project / "papers/P01/paper-contract.json", {
        "paper_id": "P01", "datasets": [], "hypotheses": [{"id": "H1"}],
        "independence": {"unique_claim_ids": ["C1"]},
    })
    write(project / "papers/P01/experiments/primary.json", {
        "paper_id": "P01", "design_id": "D1", "hypothesis_ids": ["H1"], "seeds": SEEDS,
        "stochastic": True, "run_ids": [r["run_id"] for r in runs],
        "baselines": [{"id": c} for c, role in CONDITIONS if role == "primary"],
        "ablations": ["remove-component"], "negative_controls": ["null-control"],
        "robustness_checks": ["shift", "noise"],
        "metrics": {"primary": [{"name": "synthetic_score"}], "secondary": []},
        "data_protocol": {"datasets": ["synthetic-only"]},
    })
    # A synthetic design-side lower bound tests matching, not real study power.
    write(project / "papers/P01/power-analysis.json", {
        "method": "ttest_paired", "alpha": .05/len(CONDITIONS), "required_sample_size": {"pairs": 12},
        "synthetic_component_fixture_only": True,
    })
    comparisons = []
    for condition, role in CONDITIONS:
        comparisons.append({
            "comparison_id": condition, "design_id": "D1", "hypothesis_id": "H1", "claim_ids": ["C1"],
            "role": role, "analysis_phase": "confirmatory", "comparator_id": condition,
            "metric": "synthetic_score", "dataset_id": "synthetic-only", "direction": "higher",
            "analysis_unit": "synthetic subject",
            "population_scope": "Software fixture; unit inference conditional on the fixed seeds, no scientific population.",
            "independence_rationale": "Synthetic independent identifiers used to test aggregation.",
            "assumptions": "Synthetic paired numeric data exercise the implementation only.",
            "sample_size_rationale": "Twelve independent fixture identifiers, not seventy-two repeated observations.",
            "rationale": "Synthetic coverage and decision-path validation.",
            "decision_rule": "equivalence" if role == "negative_control" else "superiority",
            "minimum_effect": .1, "alpha": .05, "family": "all-confirmatory",
            "minimum_units": 12, "analysis_mode": "paired_t", "unit_column": "unit", "value_column": "value",
            "aggregation": "mean_within_unit_then_mean_across_seeds",
            "pairs": [{"seed": seed,
                       "treatment": {"run_id": f"proposed-{seed}", "output": f"results/proposed-{seed}.csv"},
                       "comparator": {"run_id": f"{condition}-{seed}", "output": f"results/{condition}-{seed}.csv"}}
                      for seed in SEEDS],
        })
    protocol = {
        "schema_version": "1.0", "paper_id": "P01", "status": "ready_for_review",
        "pilot_run_ids": ["pilot-0"], "pilot_success_criteria": "Synthetic pilot must exit zero and retain its diagnostic.",
        "comparisons": comparisons,
        "external_validity": {"mode": "scope_limited", "rationale": "Synthetic software fixture.",
                              "claim_limit": "No real population or doctoral/publication claim."},
    }
    write(project / "papers/P01" / evidence.PLAN, protocol)
    freeze_fixture(project)
    return protocol


def claim_matrix(project: Path, report: dict, support: str = "partially_supported") -> Path:
    path = project / "reports/claim-evidence.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(results_validation.CLAIM_COLUMNS | {"comparison_ids"})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow({
            "claim_id": "C1", "paper_id": "P01", "claim": "Synthetic mixed result; not a scientific finding.",
            "evidence_ids": "synthetic-only",
            "analysis_ids": ";".join(sorted({s["run_id"] for c in report["comparisons"] for s in c["sources"]})),
            "comparison_ids": ";".join(c["comparison_id"] for c in report["comparisons"]),
            "support": support, "uncertainty": "Recent baseline is better; noise comparison is inconclusive.",
            "status": "needs_human_scientific_review",
        })
    return path


def accept(directory: Path) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    project = directory / "synthetic-study"
    fixture(project, container=True)
    errors = evidence.validate_plan(project, "P01")
    if errors:
        raise RuntimeError(errors)
    registry = runner.execute(project.name, project_root=project)
    report = evidence.build_report(project, "P01")
    write(project / "papers/P01" / evidence.REPORT, report)
    if report["status"] != "complete":
        raise RuntimeError(report["errors"])
    rows = {c["comparison_id"]: c for c in report["comparisons"]}
    assert rows["weak"]["decision"] == "meets_preregistered_threshold"
    assert rows["recent"]["decision"] == rows["noise"]["decision"] == "does_not_establish_claim"
    assert rows["recent"]["ci_high"] < 0
    assert rows["null-control"]["decision"] == "meets_preregistered_threshold"
    assert all(c["independent_units"] == 12 and c["seeds"] == 3 and c["family_size"] == 7 for c in rows.values())
    assert not results_validation.validate_claim_evidence(project, claim_matrix(project, report), registry)
    assert results_validation.validate_claim_evidence(project, claim_matrix(project, report, "supported"), registry)
    claim_matrix(project, report)
    failed = directory / "synthetic-failed-pilot"
    fixture(failed, container=True, fail_pilot=True)
    attempt = runner.execute(failed.name, ["pilot-0"], project_root=failed)[0]
    assert attempt["status"] == "failed"
    try:
        runner.execute(failed.name, ["proposed-11"], project_root=failed)
    except runner.ExperimentError:
        pass
    else:
        raise RuntimeError("failed pilot did not prevent full execution")
    assert len((failed / "experiments/registry.jsonl").read_text(encoding="utf-8").splitlines()) == 1
    receipt = {
        "schema_version": "1.0", "status": "passed", "synthetic_acceptance_only": True,
        "scientific_completion_verified": False, "paid_model_calls": 0,
        "source_commit": os.environ.get("GITHUB_SHA"), "workflow_run_id": os.environ.get("GITHUB_RUN_ID"),
        "successful_container_attempts": len(registry), "failed_pilot_attempts": 1,
        "dependent_execution_blocked": True, "comparisons": len(rows), "independent_units": 12, "seeds": 3,
        "negative_and_inconclusive_results_preserved": True, "unsupported_positive_claim_rejected": True,
        "report_sha256": evidence.sha(project / "papers/P01" / evidence.REPORT),
        "registry_sha256": evidence.sha(project / "experiments/registry.jsonl"),
        "scope": "Execution, aggregation, inferential calculations and traceability only; upstream approvals are synthetic.",
    }
    write(directory / "acceptance.json", receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(accept(args.directory.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
