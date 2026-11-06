"""Produce explicitly automated, evidence-bound quality records on the native stage.

This module performs no acquisition, model call, approval, or experiment. It
never substitutes a machine record for permission to use restricted data.
"""
from __future__ import annotations

from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import output_provenance, research_quality as quality

PROVIDER = "automated-quality-control"
ACTOR = "deterministic_control_plane"


def _target(project: Path, relative: str) -> Path:
    from scripts.paper_execution import artifact_path
    target = artifact_path(project, relative)
    if not target.resolve().is_relative_to(project.resolve()):
        raise quality.ResearchQualityError("quality record escapes the project")
    if any(p.is_symlink() for p in (target, *target.parents) if p != project.parent):
        raise quality.ResearchQualityError("quality record path contains a symlink")
    return target


def _store(project: Path, path: Path, value: dict) -> None:
    quality._atomic_json(path, value)
    output_provenance.record_model_writes(
        project, [path], family="other", provider=PROVIDER,
        model="scripts/automated_quality.py", role="automated-evidence-check",
        run_id="automated-quality",
    )


def checked_run(project: Path, stage: str) -> dict | None:
    """Use the same scientific-scope check for CLI, API and cloud quality work."""
    if not isinstance(stage, str) or stage not in {"experiment-design", "experiment-execution"}:
        return None
    blocked = {"stage": stage, "created": [], "refreshed": [], "existing": [], "blockers": [], "paid_calls": 0}
    try:
        state = quality._load_json(_target(project, "state/run.json"))
        gate = "G3" if stage == "experiment-design" else "G4"
        if (state.get("stage"), state.get("gate"), state.get("status")) != (stage, gate, "awaiting_work"):
            raise quality.ResearchQualityError("quality work requires the matching actual open G3 or G4 stage")
        from scripts.scientific_scope import validate
        issues = validate(project, gate, state.get("active_paper"))
        if issues:
            blocked["blockers"] = issues
            return blocked
        return run(project)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        blocked["blockers"].append(str(exc))
        return blocked


def run(project: Path) -> dict:
    """Run available deterministic checks and refresh controller-owned records.

    Call only after the normal stage controls and topic approvals authorize work.
    Replaced machine records are archived; unknown origins cannot be replaced.
    """
    project = project.resolve()
    state = quality._load_json(_target(project, "state/run.json"))
    stage = state.get("stage")
    if stage not in {"experiment-design", "experiment-execution"} or state.get("status") != "awaiting_work":
        raise quality.ResearchQualityError("automated quality checks require an open G3 or G4 stage")
    if state.get("gate") != ("G3" if stage == "experiment-design" else "G4"):
        raise quality.ResearchQualityError("stage and gate do not agree")
    results = {"stage": stage, "created": [], "refreshed": [], "existing": [], "blockers": [], "paid_calls": 0}
    papers = quality._paper_ids(project)
    count = state.get("paper_count")
    all_papers = [p.name for p in sorted((project / "papers").glob("P[0-9][0-9]"))]
    context = state.get("supplemental_context")
    expected_papers = ([context.get("paper_id")] if isinstance(context, dict)
                       else [f"P{n:02d}" for n in range(1, count + 1)] if type(count) is int else [])
    if not papers or (count is not None and (type(count) is not int or count != len(expected_papers) or all_papers != expected_papers)):
        results["blockers"].append("paper directories do not match the current project state")
        return results

    def ensure(relative, build, validate):
        path = _target(project, relative)
        previous = None
        if path.exists():
            try:
                value = quality._load_json(path)
                errors = validate(value)
                origin = output_provenance.current_origin(project, path)
                owned = (origin.get("status") == "tracked" and origin.get("provider") == PROVIDER
                         and origin.get("model") == "scripts/automated_quality.py")
                if value.get("confirmation_kind") == "automated":
                    if not owned:
                        errors.append("automated record lacks its control-plane provenance")
            except (quality.ResearchQualityError, OSError, ValueError) as exc:
                errors = [str(exc)]
                owned = False
            if errors and owned and value.get("confirmation_kind") == "automated":
                if stage == "experiment-design":
                    registry = _target(project, "experiments/registry.jsonl")
                    from scripts.paper_execution import enabled,selected
                    gate_key=f"G3:{selected(project)}" if enabled(project) else "G3"
                    if (registry.is_file() and registry.read_text(encoding="utf-8").strip()) or gate_key in state.get("approved_gates",[]):
                        results["blockers"].append(relative + ": frozen or executed inputs cannot be refreshed")
                        return
                    plan = _target(project, "experiments/plan.json")
                    budget = _target(project, "experiments/budget.json")
                    if plan.is_file() and budget.is_file() and any(
                        a.get("gate") == "G3" and a.get("experiment_plan_sha256") == quality.sha256_file(plan)
                        and a.get("experiment_budget_sha256") == quality.sha256_file(budget) for a in state.get("approvals", [])):
                        results["blockers"].append(relative + ": current G3 protocol is already sealed")
                        return
                previous = {"payload": value, "sha256": quality.sha256_file(path), "origin": origin, "path": relative}
            elif errors:
                results["blockers"].append(relative + ": " + "; ".join(errors))
                return
            if not errors:
                results["existing"].append(relative)
                return
        try:
            value = build()
            errors = validate(value)
            if errors:
                raise quality.ResearchQualityError("; ".join(errors))
            if previous is not None:
                archive = _target(project, "state/automated-quality-history/" + previous["sha256"] + ".json")
                if not archive.exists():
                    _store(project, archive, previous)
            _store(project, path, value)
            results["refreshed" if previous is not None else "created"].append(relative)
        except (quality.ResearchQualityError, OSError, ValueError, KeyError, TypeError) as exc:
            results["blockers"].append(relative + ": " + str(exc))

    if stage == "experiment-design":
        from scripts.paper_execution import prepare_datasets
        try:
            prepare_datasets(project)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            results["blockers"].append(str(exc))
            return results
        from scripts.research_phase import exploratory
        for dataset_id in ([] if exploratory(project) else sorted(quality._manifest_map(project))):
            if not quality.DATASET_RE.fullmatch(dataset_id):
                results["blockers"].append("invalid dataset ID")
                continue
            ensure(f"data/quality/{dataset_id}-confirmation.json",
                   lambda d=dataset_id: quality.create_data_quality_confirmation(project, d, ACTOR, automated=True),
                   lambda value, d=dataset_id: quality.validate_data_quality_confirmation(value, d, project))
        if not results["blockers"]:
            results["blockers"].extend(quality.validate_g3_quality(project, require_preregistration=False))
        if not results["blockers"]:
            for paper_id in papers:
                ensure(f"papers/{paper_id}/preregistration.json",
                       lambda p=paper_id: quality.create_preregistration(project, p, ACTOR, automated=True),
                       lambda value, p=paper_id: quality.validate_preregistration(value, p, project))
    else:
        results["blockers"].extend(quality.validate_g4_quality(project, require_confirmation=False))
        from scripts.research_phase import exploratory
        if exploratory(project):
            return results
        if not results["blockers"]:
            from scripts import study_routes
            for paper_id in papers:
                if study_routes.route(project, paper_id) != "empirical":
                    ensure(f"papers/{paper_id}/{study_routes.CONFIRMATION}",
                           lambda p=paper_id: study_routes.create_confirmation(project, p, ACTOR, automated=True),
                           lambda value, p=paper_id: study_routes.confirmation_errors(project, p, value))
                    continue
                ensure(f"papers/{paper_id}/reproduction-confirmation.json",
                       lambda p=paper_id: quality.create_reproduction_confirmation(project, p, ACTOR, automated=True),
                       lambda value, p=paper_id: quality.validate_reproduction_confirmation(value, p, project))
    return results


def main() -> int:
    import argparse
    import json
    from scripts import researchctl
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    project = researchctl.project_dir(args.project)
    stage = quality._load_json(_target(project, "state/run.json")).get("stage")
    result = checked_run(project, stage) or {"blockers": ["automated quality requires an open G3 or G4 stage"], "paid_calls": 0}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
