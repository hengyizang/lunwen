"""Continue selected research under an existing owner policy and total budget.

Historical gate records remain readable; they are not permission to do the next task.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.research_artifacts import strict_json, sha as _sha
from scripts import ai_providers, intake_validation, model_spend, researchctl

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

    try:
        value = strict_json(path.read_text(encoding="utf-8"), duplicate_error="duplicate task routing profile property")
        if (not isinstance(value, dict) or set(value) != {"schema_version", "stage", "task_profile"}
                or value["schema_version"] != "1.0"
                or not isinstance(value["task_profile"], dict)):
            raise ValueError("profile must bind schema_version 1.0 and a task profile")
        if value["stage"] != stage:
            return None  # An unrelated historical task classification cannot block new work.
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
    if stage not in {row["name"] for row in researchctl.STAGES[:-1]}:
        raise ContinuationError("routing profile needs a supported task context")
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


def task_routes(environment: Mapping[str,str], stage="topic-intelligence", project=None) -> list[dict]:
    """Resolve only this task's configured roles, without probes or global roster checks."""
    roles=["persistent-writer"]
    if project is not None:
        from scripts.research_cycle import requires_critic
        if requires_critic(stage,project):roles.append("independent-critic-initial")
    if environment.get("DR_OS_ROUTING_PROFILE")=="production" or environment.get("DR_OS_ROUTING_CONFIG"):
        from scripts import model_routing
        policy,_=model_routing.load_policy(environment)
        configured=policy["stage_routes"].get(stage,{})
        return [dict(policy["models"][configured.get(role,policy.get("default_routes",{}).get(role))]) for role in roles]
    providers=["uuapi-openai"]+(["uuapi-anthropic"] if len(roles)>1 else [])
    return [{"provider":provider,"model":ai_providers.configuration(provider,environment).get("model")} for provider in providers]


def configuration_errors(environment: Mapping[str, str], stage="topic-intelligence", project=None) -> list[str]:
    """Read exact selected route configuration; catalog availability is diagnostic only."""
    from scripts import billing_quotes
    errors=[]
    try:routes=task_routes(environment,stage,project)
    except (OSError,ValueError,KeyError,TypeError) as exc:return ["task route configuration is invalid: "+str(exc)]
    for route in routes:
        provider,model=route["provider"],route["model"]
        config=ai_providers.configuration(provider,environment)
        if not config.get("configured"):
            errors.append(config.get("configuration_error") or f"model route is not configured: {provider}")
        if config.get("strict_model_id") is False:errors.append("model response identity checking must remain enabled")
        try:
            raw=environment.get("DR_OS_MODEL_PRICING_JSON","").strip()
            if not raw and provider in ai_providers.PRODUCTION_PROVIDERS:
                raw=(researchctl.ROOT/"config/model-pricing.json").read_text(encoding="utf-8")
            prices=json.loads(raw or "{}")
            if not isinstance(prices,dict):raise ValueError("pricing must be an object")
            endpoint=ai_providers.production_endpoint(provider,model) if provider in ai_providers.PRODUCTION_PROVIDERS else config.get("endpoint","")
            if "quotes" in prices or "schema_version" in prices:
                billing_quotes.select(prices,provider,endpoint,model,config.get("billing_identity",{}))
            else:
                if provider in ai_providers.PRODUCTION_PROVIDERS:raise ValueError("production billing needs an exact conditional quote")
                key="|".join((provider,endpoint,str(model)))
                scoped=any(isinstance(k,str) and "|" in k and k.rsplit("|",1)[-1]==model for k in prices)
                price=prices.get(key if scoped else model)
                if not isinstance(price,dict):raise ValueError("missing exact model price")
                for field in ("input_per_million","output_per_million"):
                    value=price.get(field)
                    if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
                        raise ValueError("prices must be positive finite CNY values")
        except (OSError,ValueError,TypeError,KeyError):
            errors.append(f"missing or invalid exact model quote: {provider}/{model}")
    return list(dict.fromkeys(errors))


def startup_report(slug: str, environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Non-billable inspection of configuration and the restored project.

    No provider request, model probe, gate mutation, or new spending grant occurs.
    Authentication, balance and real response quality require a later authorized run.
    """
    env = os.environ if environment is None else environment
    project = researchctl.project_dir(slug)
    work=researchctl.current_work(slug) if (project/"state/run.json").is_file() else {"stage":"topic-intelligence"}
    errors = configuration_errors(env,work["stage"],project if project.exists() else None)
    try:routes=task_routes(env,work["stage"],project if project.exists() else None)
    except (OSError,ValueError,KeyError,TypeError):routes=[]
    report: dict[str, Any] = {
        "schema_version": "1.0", "project": slug, "paid_calls": 0,
        "configuration_ready": not errors, "configuration_errors": errors,
        "providers": [ai_providers.configuration(row["provider"],env) for row in routes],
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
        report["next_action"] = "Resolve the reported task input or budget issue; configuration alone does not grant new spending."
    return report


def evaluate(slug: str, environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    project=researchctl.project_dir(slug);env=os.environ if environment is None else environment
    result={"project":slug,"should_run":False,"reason":"not_enabled"}
    if not (project/POLICY).is_file():return result
    policy=_object(project/POLICY)
    if set(policy)-POLICY_FIELDS or policy.get("schema_version") not in {"1.0","2.0"} or type(policy.get("enabled")) is not bool:
        raise ContinuationError("invalid owner continuation policy")
    if not policy["enabled"]:return result
    if not isinstance(policy.get("actor"),str) or not policy["actor"].strip():
        raise ContinuationError("continuation needs the recorded owner authorization")
    try:
        confirmed=datetime.fromisoformat(policy["confirmed_at"])
        if confirmed.tzinfo is None or confirmed>datetime.now(timezone.utc):raise ValueError()
    except (KeyError,TypeError,ValueError):raise ContinuationError("owner confirmation must have a valid past timestamp") from None
    hours=policy.get("system_execution_hours_per_day",24);interval=policy.get("resume_interval_minutes",15)
    if type(hours) is not int or not 1<=hours<=24 or type(interval) is not int or not 1<=interval<=1440:
        raise ContinuationError("continuation schedule is outside its supported bounds")
    if policy.get("stop_when","manual") not in {"manual","task_complete","all_papers_submission_ready"}:
        raise ContinuationError("unsupported continuation stop condition")
    state=researchctl.load_state(slug);work=researchctl.current_work(slug)
    result.update(stage=work["stage"],gate=work["gate"],paper_id=work["paper_id"],task=work["task"],actor=policy["actor"])
    if work["status"] in {"paused","stopped","complete"}:
        return {**result,"reason":"task_"+work["status"]}
    if policy.get("stop_when")=="all_papers_submission_ready" and state.get("paper_statuses") and all(
            value=="submission_ready" for value in state["paper_statuses"].values()):
        return {**result,"reason":"all_papers_submission_ready"}
    # Intake notes, historical approvals and unrelated papers do not change the
    # actual cumulative authority. The spending ledger remains its single source.
    control=model_spend.read(project,required=True)
    remaining=control["authorized_ceiling_cny"]-control["spent_cny"]-model_spend.reserved(control)
    result.update(authorized_ceiling_cny=control["authorized_ceiling_cny"],spent_cny=control["spent_cny"],remaining_cny=round(remaining,8))
    if remaining<=0:return {**result,"reason":"cumulative_budget_boundary"}
    errors=configuration_errors(env,work["stage"],project)
    if errors:return {**result,"reason":"configuration_pending","configuration_errors":errors}
    from scripts.cloud_progress import pause_reason
    pause=pause_reason(slug)
    if pause:return {**result,**pause}
    return {**result,"should_run":True,"reason":"current_task_work_allowed"}


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


def transition_ready_gate(slug: str, decision: dict[str, Any]) -> bool:
    """Run one checked control transition under the serialized cloud job."""
    reason = decision.get("reason")
    if reason == "automatic_gate_reopen":
        state = researchctl.load_state(slug)
        if state["gate"] in {"G1", "G2"}:
            raise ContinuationError("human topic decisions cannot be reopened automatically")
        researchctl.reopen(SimpleNamespace(project=slug, note="Automatic controller reopened a legacy non-topic stage because current checks failed; no human decision or scientific approval was recorded."))
        state = researchctl.load_state(slug)
        state["history"][-1]["decision_type"] = "deterministic"
        researchctl.save_state(slug, state)
        return True
    if reason == "automatic_gate_ready":
        researchctl.mark_ready(SimpleNamespace(project=slug, note="Deterministic gate checks passed."))
        if researchctl.load_state(slug)["status"] != "approved":
            return True  # Topic selection still needs the owner's actual decision.
        researchctl.advance(SimpleNamespace(project=slug))
        return True
    if reason == "approved_gate_ready_to_advance":
        researchctl.advance(SimpleNamespace(project=slug))
        return True
    return False


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
    if value.get("should_run") is not True or value.get("reason") not in {"current_task_work_allowed", "current_stage_work_allowed"}:
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
