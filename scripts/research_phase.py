"""Research intensity within native paper plans and G3/G4 state transitions.

Exploration records observations without granting confirmatory evidence. Writing
intensity uses the existing paper contract; neither mode creates authority.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.paper_execution import paper_scoped


def phase(project: Path, paper_id: str | None = None) -> str:
    from scripts.paper_execution import artifact_path
    path = artifact_path(project, "experiments/plan.json", paper_id)
    value = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if not isinstance(value, dict):
        raise ValueError("experiment plan must be a JSON object")
    selected = value.get("research_phase", "confirmatory")
    if not isinstance(selected, str) or selected not in {"exploratory", "confirmatory"}:
        raise ValueError("research_phase must be exploratory or confirmatory")
    return selected


def exploratory(project: Path, paper_id: str | None = None) -> bool:
    return phase(project, paper_id) == "exploratory"


SUBMISSION_PENDING = "scientific writing is not final G5 clearance; enter submission preparation after the scientific checks pass"


def writing_phase(project: Path, paper_id: str | None = None) -> str:
    """Writing intensity in the existing contract/state; frozen protocols stay intact."""
    from scripts.paper_execution import state
    from scripts.research_artifacts import path_in, read
    import re
    value = state(project)
    paper = paper_id or value.get("active_paper")
    if not isinstance(paper, str) or not re.fullmatch(r"P[0-9]{2}", paper):
        return "scientific"
    contract_path = path_in(project, f"papers/{paper}/paper-contract.json", exists=False)
    contract = read(contract_path) if contract_path.is_file() else {}
    phases=value.get("writing_phases",{})
    if not isinstance(phases,dict):raise ValueError("writing_phases must map papers to their existing writing phase")
    selected = phases.get(paper, contract.get("writing_phase"))
    if selected is None:
        sealed = value.get("stage")=="submission-ready" or value.get("paper_statuses", {}).get(paper) == "submission_ready"
        sealed = sealed or f"G5:{paper}" in value.get("approved_gates", [])
        sealed = sealed or any(a.get("gate") == "G5" and a.get("paper_id", paper) == paper for a in value.get("approvals", []))
        selected = "submission" if sealed else "scientific"
    if not isinstance(selected, str) or selected not in {"scientific", "submission"}:
        raise ValueError("writing_phase must be scientific or submission")
    return selected


def requires_submission(project: Path | None, stage: str = "writing-and-review", paper_id: str | None = None) -> bool:
    if stage != "writing-and-review":
        return False
    from scripts.supplemental_experiments import proposal_pending
    return project is None or (not proposal_pending(project, paper_id) and writing_phase(project, paper_id) == "submission")


def disposition_stage(project: Path, stage: str) -> str:
    from scripts.supplemental_experiments import disposition_stage as protocol_stage
    selected = protocol_stage(project, stage)
    if selected == "writing-and-review" and not requires_submission(project, stage):
        return "scientific-writing"
    return selected


def writing_contract(project: Path, stage: str) -> str:
    if stage != "writing-and-review":
        return ""
    selected = disposition_stage(project, stage)
    if selected == "experiment-design":
        return "Review the pending supplemental protocol only; preserve its experiment-design checks. A protocol verdict cannot pass parent G5."
    if selected == "scientific-writing":
        return ("G5 SCIENTIFIC WRITING: resolve the consequential unknown using actual results, primary citations and the claim/argument record. "
                "Revise Methods, Results and the bounded contribution as evidence warrants. Preserve every adverse result and scientific disagreement. "
                "Build an evidence-led narrative around the strongest supported contribution. Keep every registered result locatable and preserve negative/null/adverse results. "
                "Retain original hypotheses and outcomes; never demote unfavorable or contentious results. State material limitations once where they change interpretation. "
                "Justify comparison scope before results and retain fixed evaluation criteria. Label post-hoc interpretations honestly; new tests still need normal approval. "
                "Assess facts, references, statistical interpretation and argument; give dispositions only for actual findings. "
                "Submission formatting and venue/package preparation are deferred; CFH/H/AD remain optional observations. "
                "After current source-bound scientific checks and the recorded research decision, the existing controller records entry into submission preparation. Advisory opinions do not authorize that transition. "
                "That transition cannot pass G5; the next G5 cycle must satisfy all final submission requirements. Never edit a frozen contract to switch phase.")
    return "G5 SUBMISSION PREPARATION: complete the three-view blind panel and source-bound venue, rendering, existing-disclosure preservation and package checks once for the unchanged final snapshot. Editorial observations remain optional; opinions and scores do not prove scientific validity."


def writing_task(project: Path, stage: str, configured: str) -> str:
    if stage=="writing-and-review":return "Work on the current paper's "+disposition_stage(project,stage)+" task."
    return "Resolve the current evidence-bearing task in "+stage+"; use the phase rules below."


def stage_rules(project: Path | None, stage: str, role: str = "writer", root: Path | None = None) -> str:
    """One config-bound scientific rule block for API and CLI ordinary tasks."""
    from scripts import scientific_reasoning
    import hashlib
    selected_root=root or Path(__file__).resolve().parents[1]
    if stage not in scientific_reasoning.STAGES:return "Use the current intake constraints; never invent an approval or research outcome."
    policy=scientific_reasoning.load_policy(selected_root)
    selected_role="writer" if role=="remediator" else role
    parts=[policy["common"],policy["roles"].get(selected_role,policy["roles"]["writer"])]
    pending=project is not None and stage=="writing-and-review" and disposition_stage(project,stage)=="experiment-design"
    exploration=project is not None and stage in {"experiment-design","experiment-execution"} and exploratory(project)
    if pending:parts.append(policy["phases"]["supplemental-protocol"])
    elif exploration:parts.append(policy["phases"]["experiment-exploration"])
    else:parts.append(policy["stages"][stage])
    if stage in {"experiment-design","experiment-execution"} and not exploration:parts.append(policy["phases"]["experiment-confirmatory"])
    if stage=="topic-intelligence":parts.append(policy["phases"]["topic-exploration"])
    if stage=="writing-and-review" and not pending:
        if project is not None and not requires_submission(project,stage):parts.append(writing_contract(project,stage))
        else:parts.append(policy["phases"]["submission"])
    path=selected_root/scientific_reasoning.POLICY
    return "Scientific reasoning contract (SHA-256 "+hashlib.sha256(path.read_bytes()).hexdigest()+"):\n"+"\n".join(parts)


def submission_only(relative: str) -> bool:
    parts = Path(relative).parts
    return (bool(parts) and parts[-1] in {"venue.json", "jcr-verification.json", "venue-compliance.json", "pre-submission-checklist.json"}
            or "submission-materials" in parts or "submission" in parts
            or relative.startswith("program/journal-dossiers"))


def enter_submission(project: Path, errors: list[str]) -> bool:
    """An explicit machine transition after all existing scientific checks pass."""
    if errors != [SUBMISSION_PENDING] or requires_submission(project):
        return False
    from datetime import datetime, timezone
    from scripts.paper_execution import state
    from scripts.research_artifacts import write
    value = state(project)
    if value.get("gate") != "G5" or value.get("status") != "awaiting_work":
        return False
    paper = value["active_paper"]
    value.setdefault("writing_phases", {})[paper] = "submission"
    value.setdefault("history", []).append({"at": datetime.now(timezone.utc).isoformat(),
        "event": "submission_preparation_started", "paper_id": paper, "decision_type": "automated"})
    value.pop("ready_gate", None)
    value.pop("ready_artifact_sha256", None)
    write(project / "state/run.json", value)
    return True


def plan_errors(plan: dict) -> list[str]:
    errors = []
    selected = plan.get("research_phase", "confirmatory")
    if not isinstance(selected, str) or selected not in {"exploratory", "confirmatory"}:
        return ["research_phase must be exploratory or confirmatory"]
    if plan.get("research_phase") == "exploratory":
        declaration = plan.get("exploration")
        if not isinstance(declaration, dict):
            return ["exploratory plans need their actual unknown and discriminating test"]
        for field in ("unknown", "discriminating_test", "continue_if", "revise_if", "stop_if", "claim_limit"):
            if not isinstance(declaration.get(field), str) or not declaration[field].strip():
                errors.append("exploration." + field + " must describe the research decision")
        if type(declaration.get("prior_outcomes_seen")) is not bool:
            errors.append("exploration.prior_outcomes_seen must declare actual prior exposure")
    return errors


def histories(project: Path, paper_id: str | None = None) -> list[dict]:
    """Read protected native history events, including every archived attempt."""
    from scripts.research_artifacts import read, path_in, sha
    from scripts.output_provenance import current_origin
    state = read(project / "state/run.json") if (project / "state/run.json").is_file() else {}
    result = []
    for event in state.get("history", []):
        if event.get("event") != "exploration_completed":
            continue
        binding = event["archive"]
        target = path_in(project, binding["path"])
        if not binding["path"].startswith("experiments/history/exploration-") or sha(target) != binding["sha256"]:
            raise ValueError("archived exploration authority changed")
        origin = current_origin(project, target)
        if (origin.get("status") != "tracked" or origin.get("provider") != "deterministic-control-plane"
                or origin.get("model") != "scripts/research_phase.py"):
            raise ValueError("archived exploration lacks controller provenance")
        value = read(target)
        if value.get("paper_id") != event.get("paper_id") or value.get("research_phase") != "exploratory":
            raise ValueError("archived exploration paper/phase changed")
        for item in value["files"]:
            if sha(path_in(project, item["archive_path"])) != item["sha256"]:
                raise ValueError("archived exploratory evidence changed: " + item["source"])
        if paper_id is None or value["paper_id"] == paper_id:
            result.append({**value, "binding": binding})
    return result


def historical_cost(project: Path) -> float:
    from scripts.experiment_runner import prior_estimated_cost
    return sum(prior_estimated_cost(project / row["registry_path"]) for row in histories(project))


def exposure_errors(project: Path, plan: dict | None = None) -> list[str]:
    from scripts.research_artifacts import read
    from scripts.paper_execution import artifact_path
    try:
        plan = plan if plan is not None else read(artifact_path(project, "experiments/plan.json"))
        papers = {row["paper_id"] for row in plan.get("runs", [])}
        history = [row for row in histories(project) if row["paper_id"] in papers]
        if not history:
            return []
        expected = [row["binding"] for row in history]
        if plan.get("prior_exploration") != expected or plan.get("prior_outcomes_seen") is not True:
            return ["a new protocol must retain every prior exploration binding and disclose prior_outcomes_seen=true"]
        if plan.get("research_phase") == "exploratory" and plan.get("exploration", {}).get("prior_outcomes_seen") is not True:
            return ["follow-up exploration must disclose its observed prior outcomes"]
        old_runs = {r["run_id"] for row in history for r in read(project / row["plan_path"])["runs"]}
        old_outputs = {o for row in history for r in read(project / row["plan_path"])["runs"] for o in r["expected_outputs"]}
        if any(r["run_id"] in old_runs or old_outputs.intersection(r["expected_outputs"]) for r in plan["runs"]):
            return ["new protocols must use new run IDs and outputs; exploration cannot be relabeled as confirmatory evidence"]
        return []
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return ["prior exploration: " + str(exc)]


def design_errors(project: Path) -> list[str]:
    """Small exploratory protocols retain data rights, exact inputs and budget."""
    from scripts.research_artifacts import read, path_in, sha
    from scripts.paper_execution import artifact_path, selected, enabled
    from scripts import experiment_runner as runner, research_quality as quality, dataset_fetch
    try:
        plan = read(artifact_path(project, "experiments/plan.json"))
        errors = plan_errors(plan) + runner.validate_plan(plan) + exposure_errors(project, plan)
        papers = {r["paper_id"] for r in plan.get("runs", [])}
        if len(papers) != 1 or (enabled(project) and papers != {selected(project)}):
            errors.append("a minimal exploration must belong to exactly the current paper")
        manifests = quality._manifest_map(project)
        wanted = set()
        for paper in papers:
            wanted.update(read(project / "papers" / paper / "paper-contract.json").get("datasets", []))
        if wanted != set(manifests):
            errors.append("exploratory dataset snapshots must exactly match the paper's declared datasets")
        raw_hashes = set()
        for identifier, manifest in manifests.items():
            errors.extend(identifier + ": " + e for e in dataset_fetch.validate_manifest(manifest))
            digest = manifest.get("download", {}).get("sha256")
            if not isinstance(digest, str) or digest == "pending":
                errors.append(identifier + ": original dataset hash is unknown")
            raw_hashes.add(digest)
        declared = set()
        for run in plan.get("runs", []):
            for item in run.get("inputs", []):
                path = path_in(project, item["path"])
                if sha(path) != item["sha256"]:
                    errors.append("exploratory input changed: " + item["path"])
                declared.add(item["sha256"])
                if "raw" in Path(item["path"]).parts and item["sha256"] not in raw_hashes:
                    errors.append("raw exploratory input needs its actual licensed dataset manifest")
        if not raw_hashes <= declared:
            errors.append("declare every selected original dataset as an exact exploratory run input")
        budget = read(artifact_path(project, "experiments/budget.json"))
        try:
            runner.compute_budget_authority(project, budget, plan)
        except runner.ExperimentError as exc:
            errors.append(str(exc))
        return errors
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        return ["exploratory design: " + str(exc)]


@paper_scoped
def preregistration_inputs(project: Path, paper_id: str) -> list[Path]:
    from scripts.research_artifacts import read, path_in
    from scripts.paper_execution import artifact_path, dataset_snapshot
    plan = read(artifact_path(project, "experiments/plan.json", paper_id))
    sources = {artifact_path(project, "experiments/plan.json", paper_id),
               artifact_path(project, "experiments/budget.json", paper_id),
               project / "papers" / paper_id / "paper-contract.json", dataset_snapshot(project, paper_id)}
    for run in plan["runs"]:
        if run["paper_id"] == paper_id:
            sources.update(path_in(project, item["path"]) for item in run["inputs"])
    from scripts.research_quality import _manifest_map
    for identifier in _manifest_map(project):
        for relative in (f"data/manifests/{identifier}.json", f"evidence/data-rights/{identifier}/metadata.json",
                         f"state/data-rights/{identifier}.json"):
            target = path_in(project, relative, exists=False)
            if target.is_file():
                sources.add(target)
    return sorted(sources)


def exploration_execution(project: Path, plan: dict, registry: list[dict]) -> dict:
    """Derive attempted, blocked and runnable work from the original receipts.

    A failed prerequisite stops its descendants, not unrelated frozen branches.
    Unexecuted descendants have no synthetic registry entry or experiment cost.
    """
    from scripts import results_validation
    from scripts.research_artifacts import read, path_in, sha
    from scripts.experiment_runner import accounted_run_cost
    attempted = {item.get("run_id") for item in registry}
    attempted_plan = {**plan, "runs": [run for run in plan["runs"] if run["run_id"] in attempted]}
    errors = results_validation.validate_registry(project, attempted_plan, registry, require_successful_retries=False)
    from scripts.primary_recovery import latest_attempt
    from scripts.paper_execution import artifact_path
    plan_hash = sha(artifact_path(project, "experiments/plan.json"))
    latest = {run_id: latest_attempt(project, run_id, registry, plan_sha256=plan_hash) for run_id in attempted}
    observations = []
    failed = {run_id for run_id, item in latest.items() if item.get("status") in {"failed", "timed_out"}
              and item.get("launch", {}).get("process_started") is True}
    unstarted = [run_id for run_id, item in latest.items() if item.get("launch", {}).get("process_started") is not True]
    for item in registry:
        receipt = path_in(project, "experiments/runs/" + item["attempt_id"] + "/run.json")
        if read(receipt) != item:
            errors.append("exploratory attempt differs from its actual executor receipt")
        integrity = item.get("input_integrity", {})
        if integrity.get("passed") is not True or integrity.get("verified_after_run") is not True:
            errors.append("exploratory observations need unchanged actual inputs, including failed attempts")
        started = item.get("launch", {}).get("process_started")
        if type(started) is not bool or (not started and item.get("status") != "failed"):
            errors.append("exploratory receipt has an inconsistent process-start/status record")
        observations.append({"attempt_id": item["attempt_id"], "run_id": item["run_id"],
            "status": item["status"], "process_started": started,
            "observation_kind": "exploratory_attempt" if started else "execution_diagnostic",
            "receipt": {"path": receipt.relative_to(project).as_posix(), "sha256": sha(receipt)},
            "outputs": item.get("outputs", []), "estimated_cost_usd": item["estimated_cost_usd"],
            "accounted_cost_usd": accounted_run_cost(item)})
    ancestors, unexecuted, pending = {}, [], []
    for run in plan["runs"]:
        causes = set()
        for parent in run.get("depends_on", []):
            if parent not in ancestors:
                raise ValueError("exploratory dependencies must retain the original acyclic plan order")
            causes.update(ancestors[parent])
            if parent in failed:
                causes.add(parent)
        ancestors[run["run_id"]] = causes
        if run["run_id"] in attempted and run["run_id"] not in unstarted:
            continue
        if causes:
            unexecuted.append({"run_id": run["run_id"], "status": "not_executed", "reason": "failed_dependency",
                "failed_run_ids": sorted(causes), "failed_attempt_ids": sorted(item["attempt_id"] for item in registry
                    if item["run_id"] in causes and item.get("status") in {"failed", "timed_out"})})
        else:
            pending.append(run["run_id"])
    return {"observations": observations, "unexecuted_runs": unexecuted, "pending_run_ids": pending,
            "unstarted_run_ids": unstarted, "all_planned_runs_executed": not unexecuted and not pending, "errors": errors}


@paper_scoped
def build_report(project: Path, paper_id: str) -> dict:
    """Inventory actual exploratory observations; never infer claim support."""
    from scripts.research_artifacts import read, sha
    from scripts.paper_execution import artifact_path, approval
    from scripts import research_quality as quality
    report = {"schema_version": "1.0", "paper_id": paper_id, "research_phase": "exploratory",
              "status": "blocked", "scientific_completion_verified": False,
              "confirmatory_evidence": False, "comparisons": [], "errors": []}
    errors = report["errors"]
    try:
        plan_path = artifact_path(project, "experiments/plan.json", paper_id)
        plan = read(plan_path)
        if plan.get("research_phase") != "exploratory":
            raise ValueError("exploratory observations need the original exploratory plan")
        errors.extend(design_errors(project))
        prereg_path = project / "papers" / paper_id / "preregistration.json"
        sealed = approval(project, "G3", paper_id) or {}
        if sealed.get("experiment_plan_sha256") != sha(plan_path) or sealed.get("frozen_protocol_sha256", {}).get(
                f"papers/{paper_id}/preregistration.json") != sha(prereg_path):
            errors.append("exploratory observations need their exact G3 protocol seal")
        errors.extend(quality.validate_preregistration(read(prereg_path), paper_id, project))
        registry = quality._registry(project)
        execution = exploration_execution(project, plan, registry)
        errors.extend(execution["errors"])
        if execution["pending_run_ids"]:
            errors.append("exploratory runs without attempts or a failed prerequisite: " + ", ".join(execution["pending_run_ids"]))
        report.update(declaration=plan["exploration"], approved_plan_sha256=sha(plan_path), implementation_sha256=sha(Path(__file__)),
                      preregistration_sha256=sha(prereg_path), observations=execution["observations"],
                      unexecuted_runs=execution["unexecuted_runs"], all_planned_runs_executed=execution["all_planned_runs_executed"],
                      execution_status="stopped_after_dependency_failure" if execution["unexecuted_runs"] else "attempts_recorded",
                      interpretation="Exploratory observations only. A new protocol and prospective evidence are required before confirmatory claims.")
        report["status"] = "complete" if not errors else "blocked"
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        errors.append(str(exc))
    return report


def archive_and_reopen(project: Path) -> None:
    """After checked exploratory G4, preserve evidence and prepare a fresh G3."""
    import shutil
    from scripts.research_artifacts import read, write, path_in, sha, record
    from scripts.paper_execution import artifact_path, selected, enabled
    state_path = project / "state/run.json"
    state = read(state_path)
    if state.get("gate") != "G4" or state.get("status") != "approved" or not exploratory(project):
        raise ValueError("only a checked exploratory G4 can return to a new G3")
    if (project / "state/experiment-execution-lease.json").exists():
        raise ValueError("an unresolved execution lease cannot be archived or reset")
    paper = selected(project) if enabled(project) else state["active_paper"]
    report = build_report(project, paper)
    if report["status"] != "complete":
        raise ValueError("; ".join(report["errors"]))
    plan_path = artifact_path(project, "experiments/plan.json")
    registry_path = artifact_path(project, "experiments/registry.jsonl")
    folder = project / "experiments/history" / ("exploration-" + paper + "-" + sha(plan_path)[:16])
    if folder.exists():
        raise ValueError("exploratory history is immutable; use a new protocol")
    frozen = project / "papers" / paper / "preregistration.json"
    sources = {plan_path, artifact_path(project, "experiments/budget.json"), registry_path, frozen,
               project / "papers" / paper / "experiment-evidence.json"}
    sources.update(project / item["path"] for item in read(frozen)["files"] if "raw" not in Path(item["path"]).parts)
    for item in report["observations"]:
        directory = project / "experiments/runs" / item["attempt_id"]
        sources.update(path for path in directory.rglob("*") if path.is_file())
        sources.update(path_in(project, output["path"]) for output in item["outputs"])
        retry = project / "state/primary-recovery/retries" / (item["attempt_id"] + ".json")
        if retry.is_file():
            sources.add(retry)
    files = []
    for source in sorted(sources):
        relative = source.relative_to(project).as_posix()
        target = folder / "files" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        files.append({"source": relative, "archive_path": target.relative_to(project).as_posix(), "sha256": sha(target)})
    manifest = folder / "manifest.json"
    archived = {item["source"]: item["archive_path"] for item in files}
    write(manifest, {"schema_version": "1.0", "research_phase": "exploratory", "paper_id": paper,
        "files": files, "plan_path": archived[plan_path.relative_to(project).as_posix()],
        "registry_path": archived[registry_path.relative_to(project).as_posix()],
        "prior_outcomes_seen": True, "confirmatory_evidence": False, "scientific_completion_verified": False})
    record(project, [manifest, *[project / item["archive_path"] for item in files]], "scripts/research_phase.py")
    binding = {"path": manifest.relative_to(project).as_posix(), "sha256": sha(manifest)}
    state.setdefault("history", []).append({"event": "exploration_completed", "paper_id": paper, "archive": binding})
    keys = {f"G3:{paper}", f"G4:{paper}"} if enabled(project) else {"G3", "G4"}
    state["approved_gates"] = [key for key in state.get("approved_gates", []) if key not in keys]
    state.update(stage_index=3, stage="experiment-design", gate="G3", status="awaiting_work")
    state.pop("ready_gate", None)
    state.pop("ready_artifact_sha256", None)
    write(state_path, state)
    prior = [row["binding"] for row in histories(project, paper)]
    write(plan_path, {"schema_version": "1.0", "status": "draft", "research_phase": "confirmatory",
        "prior_outcomes_seen": True, "prior_exploration": prior, "runs": []})
    for path in (registry_path, frozen, project / "papers" / paper / "experiment-evidence.json",
                 artifact_path(project, "experiments/quality-G3.json"), artifact_path(project, "reports/quality-G4.json")):
        path.unlink(missing_ok=True)
    record(project, [state_path, plan_path], "scripts/research_phase.py")
