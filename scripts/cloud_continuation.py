"""Evaluate owner-confirmed continuous work without granting gates or spending.

One serialized cloud job runs one bounded API cycle. Successful work can request
the next job; cron only supplies recovery wakeups. Every job re-reads the project,
the original owner confirmation, exact constraints and the cumulative ledger.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

try:
    from scripts import ai_providers, intake_validation, model_runtime, model_spend, researchctl
except ImportError:
    import ai_providers  # type: ignore
    import intake_validation  # type: ignore
    import model_runtime  # type: ignore
    import model_spend  # type: ignore
    import researchctl  # type: ignore

POLICY = Path("state/continuation.json")
STATUS = Path("state/continuation-status.json")
TASK_PROFILE = Path("state/task-routing-profile.json")
CONFIG = ("UUAPI_ANTHROPIC_MODEL", "UUAPI_OPENAI_MODEL", "DR_OS_MODEL_PRICING_JSON")
POLICY_FIELDS = {"schema_version", "enabled", "actor", "confirmed_at", "confirmation_note",
                 "system_execution_hours_per_day", "resume_interval_minutes", "constraints_sha256",
                 "g0_approval_artifact_sha256", "stop_when"}


class ContinuationError(RuntimeError):
    pass


def task_profile(project: Path, stage: str) -> dict[str, Any] | None:
    """Read one explicit stage-bound profile; absence means unknown, never routine.

    This fixed control path is optional and does not confer spending or scientific
    authority. Stale, malformed or redirected profiles stop before model calls.
    """
    path = project / TASK_PROFILE
    if project.is_symlink() or (project / "state").is_symlink() or path.is_symlink():
        raise ContinuationError("task routing profile cannot use symlinks")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 16000:
        raise ContinuationError("task routing profile must be a bounded JSON control file")

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate task routing profile property")
            value[key] = item
        return value

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
        if (not isinstance(value, dict) or set(value) != {"schema_version", "stage", "task_profile"}
                or value["schema_version"] != "1.0" or value["stage"] != stage
                or not isinstance(value["task_profile"], dict)):
            raise ValueError("profile must bind schema_version 1.0 and the exact current stage")
        from scripts import dynamic_routing
        return dynamic_routing.validate_profile(value["task_profile"], stage=stage,
                                                role="persistent-writer")
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        raise ContinuationError(f"invalid task routing profile: {exc}") from exc


def set_task_profile(project: Path, stage: str, profile: dict, *, actor: str, run_id: str,
                     expected_profile_sha256: str | None = None) -> dict[str, Any]:
    """Apply an authenticated manager declaration without changing stage or budget."""
    from scripts import dynamic_routing, output_provenance
    from scripts.research_artifacts import path_in, write
    state = _object(path_in(project, "state/run.json"))
    if stage != state.get("stage"):
        raise ContinuationError("routing profile must bind the current persisted stage")
    if not isinstance(profile, dict):
        raise ContinuationError("routing task profile must be a JSON object")
    normalized = dynamic_routing.validate_profile(profile, stage=stage, role="persistent-writer")
    if not isinstance(actor, str) or not actor.strip() or not isinstance(run_id, str) or not run_id:
        raise ContinuationError("routing profile requires an authenticated actor and run ID")
    path = path_in(project, TASK_PROFILE.as_posix(), exists=False)
    if expected_profile_sha256 is not None and (not isinstance(expected_profile_sha256, str)
            or not re.fullmatch(r"[a-f0-9]{64}", expected_profile_sha256)):
        raise ContinuationError("routing profile expected hash must be lowercase SHA-256")
    previous = None
    if path.exists():
        if not path.is_file() or path.stat().st_size > 16000:
            raise ContinuationError("existing routing profile is not a bounded control file")
        previous = _sha(path)
        if expected_profile_sha256 != previous:
            raise ContinuationError("existing routing profile changed; supply its exact current hash")
    elif expected_profile_sha256 is not None:
        raise ContinuationError("expected routing profile is missing")
    path_in(project, output_provenance.REGISTRY_RELATIVE.as_posix(), exists=False)
    write(path, {"schema_version": "1.0", "stage": stage, "task_profile": normalized})
    output_provenance.record_model_writes(project, [path], family="other",
        provider="deterministic-control-plane", model="scripts/cloud_continuation.py",
        role="manager-task-declaration", run_id=run_id)
    return {"schema_version": "1.0", "operation": "set_routing_profile", "actor": actor,
            "run_id": run_id, "stage": stage, "task_profile": normalized,
            "previous_sha256": previous, "profile_sha256": _sha(path), "paid_calls_executed": 0,
            "budget_granted_cny": 0, "scientific_gate_approved": False}


def _object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContinuationError(f"unreadable control file: {path.name}") from exc
    if not isinstance(value, dict):
        raise ContinuationError(f"control file must contain an object: {path.name}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configuration_errors(environment: Mapping[str, str]) -> list[str]:
    """Use the same resolver as transport; return labels without secret values."""
    if environment.get("DR_OS_ROUTING_PROFILE") == "production":
        from scripts.production_readiness import report
        return report(environment)["configuration_errors"]
    errors: list[str] = []
    providers = [ai_providers.configuration(provider, environment)
                 for provider in ("uuapi-openai", "uuapi-anthropic")]
    for provider in providers:
        if provider["configuration_error"]:
            errors.append(provider["configuration_error"])
        if not provider["strict_model_id"]:
            errors.append("cloud execution requires UUAPI_STRICT_MODEL_ID=true")
    models = [provider["model"] for provider in providers]
    if all(models) and models[0] == models[1]:
        errors.append("author and critic must use distinct exact model IDs")
    if not environment.get("DR_OS_MODEL_PRICING_JSON", "").strip():
        errors.append("missing DR_OS_MODEL_PRICING_JSON")
    else:
        try:
            rates = json.loads(environment["DR_OS_MODEL_PRICING_JSON"])
            if not isinstance(rates, dict):
                raise ValueError("not an object")
            for model in models:
                price = rates.get(model)
                if not isinstance(price, dict):
                    raise ValueError("missing exact model price")
                for key in ("input_per_million", "output_per_million"):
                    number = price.get(key)
                    if (not isinstance(number, (int, float)) or isinstance(number, bool)
                            or not math.isfinite(number) or number <= 0):
                        raise ValueError("invalid price")
        except (ValueError, TypeError, KeyError):
            errors.append("DR_OS_MODEL_PRICING_JSON needs positive finite CNY input/output prices for both exact model IDs")
    return list(dict.fromkeys(errors))


def startup_report(slug: str, environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Non-billable inspection of configuration and the restored project.

    No provider request, model probe, gate mutation, or new spending grant occurs.
    Authentication, balance and real response quality require a later authorized run.
    """
    env = os.environ if environment is None else environment
    errors = configuration_errors(env)
    report: dict[str, Any] = {
        "schema_version": "1.0", "project": slug, "paid_calls": 0,
        "configuration_ready": not errors, "configuration_errors": errors,
        "providers": [ai_providers.configuration(provider, env)
                      for provider in (tuple(ai_providers.PRODUCTION_PROVIDERS)
                                       if env.get("DR_OS_ROUTING_PROFILE")=="production"
                                       else ("uuapi-openai", "uuapi-anthropic"))],
        "ready_to_continue": False, "provider_authentication_verified": False,
        "scientific_completion_verified": False,
        "next_action": "Configure missing fields, then rerun the non-billable check.",
    }
    project = researchctl.project_dir(slug)
    if not (project / "state/run.json").is_file():
        report["continuation"] = {"should_run": False, "reason": "project_not_initialized"}
        return report
    try:
        state = researchctl.load_state(slug)
        report["current_state"] = {key: state.get(key) for key in ("stage", "gate", "status", "active_paper")}
        control = model_spend.read(project, required=True)
        assert control is not None
        report["budget"] = {
            "authorized_ceiling_cny": control["authorized_ceiling_cny"],
            "spent_cny": control["spent_cny"],
            "reserved_cny": model_spend.reserved(control),
            "remaining_cny": round(control["authorized_ceiling_cny"] - control["spent_cny"]
                                   - model_spend.reserved(control), 8),
        }
        decision = evaluate(slug, env)
    except (RuntimeError, ValueError, OSError, KeyError, TypeError):
        decision = {"should_run": False, "reason": "project_control_validation_failed"}
    report["continuation"] = decision
    report["ready_to_continue"] = not errors and decision["should_run"]
    if report["ready_to_continue"]:
        report["next_action"] = ("Run the start mode to begin an authorized cloud cycle. "
                                 "Each request reserves budget before transport; real authentication is not yet verified.")
    elif not errors:
        report["next_action"] = "Resolve the reported project, human-review or budget blocker; configuration alone does not grant authority."
    return report


def evaluate(slug: str, environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    project = researchctl.project_dir(slug)
    env = os.environ if environment is None else environment
    result: dict[str, Any] = {"project": slug, "should_run": False, "reason": "not_enabled"}
    if not (project / POLICY).is_file():
        return result
    policy = _object(project / POLICY)
    if (set(policy) != POLICY_FIELDS or policy.get("schema_version") != "1.0"
            or type(policy.get("enabled")) is not bool):
        raise ContinuationError("invalid owner continuation policy")
    if not policy["enabled"]:
        return result
    if (policy["system_execution_hours_per_day"] != 24 or type(policy["system_execution_hours_per_day"]) is not int
            or policy["resume_interval_minutes"] != 15 or type(policy["resume_interval_minutes"]) is not int
            or policy["stop_when"] != "all_papers_submission_ready"):
        raise ContinuationError("unsupported continuation schedule or stop condition")
    for field in ("actor", "confirmation_note"):
        if not isinstance(policy.get(field), str) or not policy[field].strip():
            raise ContinuationError("a named owner confirmation is required")
    try:
        confirmed = datetime.fromisoformat(policy["confirmed_at"])
        if confirmed.tzinfo is None or confirmed > datetime.now(timezone.utc):
            raise ValueError("invalid confirmation time")
    except (TypeError, ValueError):
        raise ContinuationError("owner confirmation must have a valid past timestamp") from None
    for field in ("constraints_sha256", "g0_approval_artifact_sha256"):
        if not isinstance(policy.get(field), str) or not re.fullmatch(r"[a-f0-9]{64}", policy[field]):
            raise ContinuationError("owner confirmation needs exact input hashes")
    constraints_path = project / "intake/constraints.json"
    if not constraints_path.is_file() or _sha(constraints_path) != policy["constraints_sha256"]:
        return {**result, "reason": "constraints_changed_since_confirmation"}
    constraints = _object(constraints_path)
    if (intake_validation.validate_constraints(constraints)
            or constraints.get("execution_mode") != "cloud_only"
            or constraints.get("system_execution_hours_per_day") != 24):
        return {**result, "reason": "invalid_cloud_constraints"}
    state = researchctl.load_state(slug)
    approvals = state.get("approvals", [])
    gates = state.get("approved_gates", [])
    if (not isinstance(approvals, list) or any(not isinstance(item, dict) for item in approvals)
            or not isinstance(gates, list) or any(not isinstance(item, str) for item in gates)
            or type(state.get("stage_index")) is not int):
        raise ContinuationError("invalid scientific approval records")
    approved = set(gates)
    g0 = next((item for item in reversed(approvals) if item.get("gate") == "G0"), None)
    if ("G0" not in approved or not g0 or g0.get("actor") != policy["actor"]
            or g0.get("artifact_sha256") != policy["g0_approval_artifact_sha256"]):
        return {**result, "reason": "g0_confirmation_pending"}
    result.update({"stage": state["stage"], "gate": state["gate"], "actor": policy["actor"]})
    count = state.get("paper_count")
    if type(count) is not int or not 1 <= count <= 20:
        raise ContinuationError("invalid paper portfolio size")
    paper_ids = [f"P{index:02d}" for index in range(1, count + 1)]
    required = [f"G{index}" for index in range(min(state["stage_index"], 5))]
    if any(gate not in approved or not any(item.get("gate") == gate for item in approvals) for gate in required):
        return {**result, "reason": "prior_human_gate_missing"}
    if state["gate"] is None:
        if state["status"] != "submission_ready":
            return {**result, "reason": "incomplete_paper_portfolio"}
        for paper_id in paper_ids:
            approval = next((item for item in reversed(approvals)
                             if item.get("gate") == "G5" and item.get("paper_id") == paper_id), None)
            if (state.get("paper_statuses", {}).get(paper_id) != "submission_ready"
                    or f"G5:{paper_id}" not in approved or not approval
                    or not approval.get("actor", "").strip()
                    or approval.get("paper_artifact_sha256") != researchctl.paper_artifact_hash(slug, paper_id)):
                return {**result, "reason": "incomplete_or_changed_paper_approval"}
        return {**result, "reason": "all_papers_submission_ready"}
    if state["gate"] == "G0" or state["status"] in {"awaiting_approval", "approved"}:
        return {**result, "reason": "human_gate_pending"}
    if not researchctl.gate_errors(slug, state["gate"]):
        return {**result, "reason": "human_gate_pending"}
    control = model_spend.read(project, required=True)
    assert control is not None
    remaining = control["authorized_ceiling_cny"] - control["spent_cny"] - model_spend.reserved(control)
    result.update({"authorized_ceiling_cny": control["authorized_ceiling_cny"],
                   "spent_cny": control["spent_cny"], "remaining_cny": round(remaining, 8)})
    if control["reservations"]:
        return {**result, "reason": "billing_reconciliation_pending"}
    if remaining <= 0:
        return {**result, "reason": "cumulative_budget_boundary"}
    budget = model_runtime.budget_status(project, state["active_paper"])
    if budget["paper_remaining"] <= 0:
        return {**result, "reason": "paper_budget_boundary"}
    errors = configuration_errors(env)
    if errors:
        return {**result, "reason": "configuration_pending", "configuration_errors": errors}
    if env.get("DR_OS_ROUTING_PROFILE")=="production" and env.get("DR_OS_AUTOMATIC_RESEARCH_ENABLED")!="true":
        return {**result,"reason":"production_configured_automatic_research_not_started"}
    previous = _object(project / STATUS) if (project / STATUS).is_file() else {}
    if previous.get("last_cycle_exit_code", 0) != 0:
        return {**result, "reason": "previous_cycle_failed_requires_inspection"}
    from scripts.cloud_progress import pause_reason
    pause = pause_reason(slug)
    if pause:
        return {**result, **pause}
    return {**result, "should_run": True, "reason": "current_stage_work_allowed"}


def checkpoint(slug: str, decision: dict[str, Any], run_id: str,
               *, cycle_exit_code: int | None = None) -> None:
    project = researchctl.project_dir(slug)
    previous = _object(project / STATUS) if (project / STATUS).is_file() else {}
    value = {"schema_version": "1.0", **decision}
    if cycle_exit_code is not None:
        value["last_cycle_exit_code"] = cycle_exit_code
    elif "last_cycle_exit_code" in previous:
        value["last_cycle_exit_code"] = previous["last_cycle_exit_code"]
    compared = {key: item for key, item in previous.items() if key not in {"changed_at", "source_run_id"}}
    if value != compared:
        value.update({"changed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                      "source_run_id": run_id})
        researchctl.write_json(project / STATUS, value)


def scheduled_request(event: dict[str, Any], environment: Mapping[str, str]) -> dict[str, Any]:
    try:
        from scripts import cloud_job
    except ImportError:
        import cloud_job  # type: ignore
    repository = event.get("repository") or {}
    if (repository.get("full_name") != cloud_job.REPOSITORY
            or (repository.get("owner") or {}).get("id") != cloud_job.OWNER_ID
            or environment.get("GITHUB_REPOSITORY") != cloud_job.REPOSITORY
            or environment.get("GITHUB_REF") != "refs/heads/main"
            or environment.get("GITHUB_EVENT_NAME") not in {"schedule", "workflow_dispatch"}):
        raise ContinuationError("continuation only runs in the owner's main cloud workflow")
    if (environment["GITHUB_EVENT_NAME"] == "workflow_dispatch"
            and (event.get("sender") or {}).get("id") not in {cloud_job.OWNER_ID, 41898282}):
        raise ContinuationError("manual wakeup must come from the owner or the workflow bot")
    mode = "start" if environment["GITHUB_EVENT_NAME"] == "schedule" else (event.get("inputs") or {}).get("mode", "check")
    if mode not in {"check", "start"}:
        raise ContinuationError("manual mode must be check or start")
    action = "preflight" if mode == "check" else "continuation"
    return cloud_job.validate_request({"schema_version": "1.0", "action": action,
                                      "project": "my-phd", "actor": "Hengyi Zang", "allow_paid": mode == "start"})


def enqueue_followup(path: Path) -> int:
    """Only dispatch an identical controller, or stop its completed schedule."""
    try:
        from scripts import cloud_job
    except ImportError:
        import cloud_job  # type: ignore
    value = _object(path)
    if value.get("project") != "my-phd":
        raise ContinuationError("unexpected followup project")
    if value.get("reason") == "all_papers_submission_ready":
        return subprocess.run(["gh", "api", "--method", "PUT",
                               f"repos/{cloud_job.REPOSITORY}/actions/workflows/research-continuation.yml/disable"],
                              check=False).returncode
    if value.get("should_run") is not True or value.get("reason") != "current_stage_work_allowed":
        print("Continuation paused: " + str(value.get("reason", "unknown")))
        return 0
    return subprocess.run(["gh", "workflow", "run", "research-continuation.yml", "--ref", "main",
                           "--repo", cloud_job.REPOSITORY, "-f", "mode=start"], check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    request = sub.add_parser("scheduled-request")
    request.add_argument("--event", type=Path, required=True)
    request.add_argument("--output", type=Path, required=True)
    followup = sub.add_parser("enqueue-followup")
    followup.add_argument("--decision", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "scheduled-request":
            value = scheduled_request(_object(args.event), os.environ)
            researchctl.write_json(args.output, value)
            return 0
        return enqueue_followup(args.decision)
    except (ContinuationError, OSError, ValueError) as exc:
        print(f"continuation: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
