"""Evidence-bound primary recovery with bounded automatic no-start retries."""
from __future__ import annotations

import hashlib
import errno
import json
import math
import os
import re
import shutil
from pathlib import Path

CONTROL = "state/primary-recovery"
HISTORY = "experiments/history"
AUTOMATIC_PROPOSAL = "program/primary-recovery.json"
MODULE = "scripts/primary_recovery.py"


from scripts.paper_execution import artifact_path as experiment_path

class RecoveryError(ValueError):
    pass


try:
    from scripts.research_artifacts import load_json as read, sha
except ImportError:
    from research_artifacts import load_json as read, sha


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def path_in(project, relative):
    from scripts.cloud_checkpoint import relative as safe_relative
    safe_relative(relative)
    target = project / relative
    if any(p.is_symlink() for p in (target, *target.parents)) or project.resolve() not in target.resolve().parents:
        raise RecoveryError("recovery paths must be ordinary files inside the project")
    return target


def records(project):
    path = experiment_path(project, 'experiments/registry.jsonl')
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def receipt(project, item):
    attempt = item.get("attempt_id", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,110}", attempt):
        raise RecoveryError("invalid executor attempt")
    path = path_in(project, f"experiments/runs/{attempt}/run.json")
    if not path.is_file() or read(path) != item:
        raise RecoveryError("attempt has no unchanged executor receipt")
    return path


def _approval(project, item):
    path = project / CONTROL / "retries" / (item["attempt_id"] + ".json")
    if not path.exists():
        return None
    approval = read(path)
    if (approval.get("failed_receipt_sha256") != sha(receipt(project, item))
            or approval.get("plan_sha256") != item.get("approved_plan_sha256")
            or approval.get("plan_sha256") != sha(experiment_path(project, 'experiments/plan.json'))
            or not approval.get("actor")):
        raise RecoveryError("primary retry authorization is stale")
    if approval.get("decision_kind") == "automated":
        from scripts.output_provenance import current_origin
        origin = current_origin(project, path)
        if (origin.get("status") != "tracked" or origin.get("provider") != "deterministic-control-plane"
                or origin.get("model") != "scripts/primary_recovery.py"
                or approval.get("actor") != "deterministic_control_plane"
                or approval.get("human_confirmation") is not False
                or approval.get("next_attempt_number") != 2
                or approval.get("budget_sha256") != sha(experiment_path(project, 'experiments/budget.json'))
                or approval.get("diagnosis") != _no_start_evidence(project, item)):
            raise RecoveryError("automatic primary recovery evidence is stale")
    elif not approval.get("cloud_review_sha256"):
        raise RecoveryError("primary retry lacks its recorded recovery decision")
    for row in approval["preserved_outputs"]:
        target = path_in(project, row["preserved_path"])
        if not target.is_file() or sha(target) != row["sha256"]:
            raise RecoveryError("preserved failed output changed")
    return approval


def preserved_output(project, item, output):
    """A failed result overwritten by an authorized retry remains independently readable."""
    approval = _approval(project, item)
    if not approval:
        return path_in(project, output["path"])
    matches = [r for r in approval["preserved_outputs"] if r["path"] == output["path"] and r["sha256"] == output["sha256"]]
    if len(matches) != 1:
        raise RecoveryError("failed output is absent from the reviewed recovery archive")
    return path_in(project, matches[0]["preserved_path"])


def _original_input(project, relative, expected_hash):
    target = path_in(project, relative)
    if not target.is_file() or sha(target) != str(expected_hash).lower():
        raise RecoveryError("original frozen input is missing or changed: " + relative)
    return target


def _retained_output(project, item, output):
    target = (preserved_output(project, item, output) if item["status"] in {"failed", "timed_out"}
              else path_in(project, output["path"]))
    if not target.is_file() or sha(target) != output["sha256"]:
        raise RecoveryError("retired executor output is missing or changed")
    return {"path": target.relative_to(project).as_posix(), "sha256": output["sha256"],
            "original_path": output["path"], "attempt_id": item["attempt_id"]}


def latest_attempt(project, run_id, rows, *, plan_sha256=None):
    """Validate the original retry chain without calling a failed attempt successful."""
    attempts = [r for r in rows if r.get("run_id") == run_id]
    if not attempts:
        raise RecoveryError("run has no executor attempt")
    if len({r.get("attempt_id") for r in attempts}) != len(attempts):
        raise RecoveryError("duplicate executor attempts")
    # Preserve compatibility for ordinary receipts; callers still validate their contents.
    if len(attempts) == 1:
        item = attempts[0]
    else:
        for index, failed in enumerate(attempts[:-1]):
            if failed.get("status") not in {"failed", "timed_out"}:
                raise RecoveryError("successful runs cannot be rerun to select a better result")
            approval = _approval(project, failed)
            if not approval or approval["next_attempt_number"] != index + 2:
                raise RecoveryError("each repeated attempt requires its own exact recovery decision")
            if attempts[index + 1].get("attempt_id") != f"{run_id}-attempt-{index + 2:03d}":
                raise RecoveryError("retry did not use its reviewed next attempt")
        item = attempts[-1]
    if plan_sha256 and item.get("approved_plan_sha256") != plan_sha256:
        raise RecoveryError("run has no current approved attempt")
    return item


def selected_attempt(project, run_id, rows, *, plan_sha256=None):
    item = latest_attempt(project, run_id, rows)
    if item.get("status") != "succeeded" or (plan_sha256 and item.get("approved_plan_sha256") != plan_sha256):
        raise RecoveryError("run has no current successful approved attempt")
    return item


def require_next_attempt(project, run_id, rows, plan_sha256):
    attempts = [r for r in rows if r.get("run_id") == run_id]
    if not attempts:
        return
    if any(r.get("status") == "succeeded" for r in attempts):
        raise RecoveryError("successful primary runs cannot be rerun")
    for index, item in enumerate(attempts):
        receipt(project, item)
        authorization = _approval(project, item)
        if (not authorization or item.get("approved_plan_sha256") != plan_sha256
                or authorization["next_attempt_number"] != index + 2):
            raise RecoveryError("failed primary attempt needs exact recovery authorization before retry")


def _no_start_evidence(project, item):
    """Recognize executor-issued launch failures; never classify from prose."""
    launch = item.get("launch", {})
    if (item.get("status") != "failed" or item.get("timed_out") is not False
            or item.get("exit_code") is not None or launch.get("process_started") is not False
            or launch.get("failure_kind") != "process_launch_oserror"
            or type(launch.get("os_error_errno")) is not int
            or launch["os_error_errno"] not in {errno.ENOENT, errno.EACCES}
            or item.get("outputs") != [] or item.get("preexisting_output_snapshots") != []
            or item.get("input_integrity", {}).get("passed") is not True
            or item.get("input_integrity", {}).get("verified_after_run") is not True):
        raise RecoveryError("failure is not a proven unchanged pre-process launch failure")
    if item.get("attempt_id") != item.get("run_id", "") + "-attempt-001":
        raise RecoveryError("one automatic recovery attempt per run is the hard limit")
    logs = item.get("logs", {})
    bindings = []
    for name in ("stdout", "stderr"):
        relative = logs.get(name)
        expected = f"experiments/runs/{item['attempt_id']}/{name}.txt"
        if relative != expected or logs.get(name + "_truncated") is not False:
            raise RecoveryError("complete original executor logs are required")
        target = path_in(project, relative)
        if not target.is_file() or target.stat().st_size:
            raise RecoveryError("a no-start failure must retain empty process-output logs")
        bindings.append({"path": relative, "sha256": sha(target)})
    return {"failure_kind": launch["failure_kind"], "process_started": False,
            "os_error_errno": launch["os_error_errno"], "logs": bindings,
            "maximum_automatic_retries": 1}


def automatic_retry(project, item):
    """Authorize at most one unchanged retry within the project total.

    Running leases, scientific/nonzero exits, outputs, timeouts,
    or changed frozen inputs remain explicit machine diagnostic blockers.
    This function never runs an experiment or changes the approved protocol.
    """
    from scripts import experiment_runner as runner
    from scripts.supplemental_experiments import all_compute_cost
    from scripts.research_artifacts import record, write as atomic_write
    if not isinstance(item, dict) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,110}", str(item.get("attempt_id", ""))):
        raise RecoveryError("invalid executor attempt for machine diagnosis")
    diagnostic_path = project / CONTROL / "diagnostics" / (item["attempt_id"] + ".json")
    result = {"attempt_id": item["attempt_id"], "retry_authorized": False,
              "decision_kind": "automated", "human_confirmation": False}
    try:
        state = read(project / "state/run.json")
        if state.get("gate") != "G4" or state.get("status") != "awaiting_work":
            raise RecoveryError("automatic recovery requires the open G4 stage")
        receipt(project, item)
        if (project / "state/experiment-execution-lease.json").exists():
            raise RecoveryError("execution reservation is unresolved; no automatic retry")
        plan, ceiling = runner.approved_plan(project, experiment_path(project, 'experiments/plan.json'), experiment_path(project, 'experiments/budget.json'))
        rows = records(project)
        attempts = [r for r in rows if r.get("run_id") == item.get("run_id")]
        if attempts != [item]:
            raise RecoveryError("one automatic recovery attempt per run is the hard limit")
        diagnosis = _no_start_evidence(project, item)
        matches = [r for r in plan["runs"] if r["run_id"] == item.get("run_id")]
        if len(matches) != 1 or item.get("approved_plan_sha256") != sha(experiment_path(project, 'experiments/plan.json')):
            raise RecoveryError("failed attempt differs from the approved plan")
        run = matches[0]
        if item.get("cwd") != run.get("cwd", "."):
            raise RecoveryError("failed attempt working directory differs from the frozen plan")
        for field in ("argv", "seed", "timeout_seconds"):
            if item.get(field) != run.get(field):
                raise RecoveryError("failed attempt configuration differs from the frozen plan")
        if item.get("estimated_cost_usd") != float(run["estimated_cost_usd"]):
            raise RecoveryError("failed attempt has unresolved cost accounting")
        for source in run["inputs"]:
            _original_input(project, source["path"], source["sha256"])
        program = run["isolation"].get("engine") if run["isolation"]["kind"] == "container" else run["argv"][0]
        if not shutil.which(program):
            raise RecoveryError("required executor is still unavailable; no automatic retry")
        committed = all_compute_cost(runner.compute_project(project))
        requested = float(run["estimated_cost_usd"])
        if not math.isfinite(committed + requested) or committed + requested > ceiling:
            raise RecoveryError("automatic retry exceeds the unchanged cumulative compute budget")
        authorization = project / CONTROL / "retries" / (item["attempt_id"] + ".json")
        if authorization.exists():
            _approval(project, item)
        else:
            value = {"decision_kind": "automated", "human_confirmation": False,
                     "actor": "deterministic_control_plane", "plan_sha256": sha(experiment_path(project, 'experiments/plan.json')),
                     "budget_sha256": sha(experiment_path(project, 'experiments/budget.json')),
                     "failed_receipt_sha256": sha(receipt(project, item)), "next_attempt_number": 2,
                     "preserved_outputs": [], "diagnosis": diagnosis,
                     "budget_check": {"committed_usd": committed, "next_estimate_usd": requested, "ceiling_usd": ceiling}}
            atomic_write(authorization, value)
            record(project, [authorization], "scripts/primary_recovery.py")
        result.update(retry_authorized=True, diagnosis=diagnosis)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        result["blocker"] = str(exc)
    if not diagnostic_path.exists() or read(diagnostic_path) != result:
        atomic_write(diagnostic_path, result)
        record(project, [diagnostic_path], "scripts/primary_recovery.py")
    return result


def diagnosis_context(project):
    """Free failure packet for the existing author/critic cycle, never execution.

    Automatic protocol withdrawal is intentionally narrower than human legacy
    recovery: no completed scientific outcome may be discarded, and only one
    withdrawal is allowed. Failed attempts retain conservatively accounted
    estimated costs; altered evidence or active executions remain blocked.
    """
    result = {"status": "not_needed", "paid_calls": 0, "execution_authorized": False}
    try:
        state = read(project / "state/run.json")
        if (state.get("gate"), state.get("status")) != ("G4", "awaiting_work"):
            return result
        rows = records(project)
        if not any(row.get("status") in {"failed", "timed_out"} for row in rows):
            return result
        from scripts import experiment_runner as runner, scientific_scope
        from scripts.supplemental_experiments import all_compute_cost
        if (project / "state/experiment-execution-lease.json").exists():
            raise RecoveryError("execution reservation is unresolved")
        previous = histories(project)
        if any(row.get("decision_kind") == "automated" for row in previous):
            raise RecoveryError("one automatic primary protocol retirement is the hard limit")
        if any(row.get("status") not in {"failed", "timed_out"} for row in rows):
            raise RecoveryError("automatic retirement cannot discard or rerun a completed scientific outcome")
        errors = scientific_scope.validate(project, "G4")
        if errors:
            raise RecoveryError("; ".join(errors))
        plan, ceiling = runner.approved_plan(project, experiment_path(project, 'experiments/plan.json'), experiment_path(project, 'experiments/budget.json'))
        planned = {row["run_id"]: row for row in plan["runs"]}
        if not rows or len(rows) > 100 or len({row.get("attempt_id") for row in rows}) != len(rows):
            raise RecoveryError("bounded unique failed executor attempts are required")
        evidence, failure_logs, log_bytes = [], [], 0
        for item in rows:
            source = receipt(project, item)
            run = planned.get(item.get("run_id"), {})
            if (item.get("approved_plan_sha256") != sha(experiment_path(project, 'experiments/plan.json'))
                    or item.get("launch", {}).get("process_started") is not True
                    or item.get("input_integrity", {}).get("passed") is not True
                    or item.get("input_integrity", {}).get("verified_after_run") is not True
                    or item.get("paper_id") != run.get("paper_id")
                    or item.get("cwd") != run.get("cwd", ".")
                    or any(item.get(key) != run.get(key) for key in ("argv", "seed", "timeout_seconds"))):
                raise RecoveryError("failure lacks unchanged frozen inputs and actual process execution evidence")
            estimate = item.get("estimated_cost_usd")
            if (type(estimate) not in (float, int) or not math.isfinite(estimate) or estimate < 0
                    or estimate != run.get("estimated_cost_usd")):
                raise RecoveryError("failed attempt cost is unresolved")
            runner.accounted_run_cost(item)
            evidence.append({"path": source.relative_to(project).as_posix(), "sha256": sha(source)})
            for name in ("stdout", "stderr"):
                relative = f"experiments/runs/{item['attempt_id']}/{name}.txt"
                if item.get("logs", {}).get(name) != relative or item.get("logs", {}).get(name + "_truncated") is not False:
                    raise RecoveryError("complete original failed-process logs are required")
                log = path_in(project, relative)
                if not log.is_file():
                    raise RecoveryError("failed-process log is missing")
                log_bytes += log.stat().st_size
                if log_bytes > 64_000:
                    raise RecoveryError("complete failure logs exceed the bounded automatic diagnosis packet")
                content = log.read_bytes().decode("utf-8")
                from urllib.parse import quote
                credentials = [value for key, value in os.environ.items()
                               if re.search(r"KEY|SECRET|TOKEN|PASSWORD", key, re.I) and len(value) >= 8]
                if any(value in content or quote(value, safe="") in content for value in credentials):
                    raise RecoveryError("configured credential detected in retained executor output; automatic model diagnosis is blocked")
                evidence.append({"path": relative, "sha256": sha(log)})
                failure_logs.append({"path": relative, "sha256": sha(log), "text": content,
                                     "untrusted_executor_output": True})
            for output in item.get("outputs", []):
                retained = _retained_output(project, item, output)
                evidence.append({"path": retained["path"], "sha256": retained["sha256"]})
            for output in item.get("preexisting_output_snapshots", []):
                target = _original_input(project, output["snapshot_path"], output["sha256"])
                evidence.append({"path": target.relative_to(project).as_posix(), "sha256": sha(target)})
        for run in plan["runs"]:
            for item in run["inputs"]:
                _original_input(project, item["path"], item["sha256"])
        for prereg in (project / "papers").glob("P[0-9][0-9]/preregistration.json"):
            for item in read(prereg).get("files", []):
                _original_input(project, item["path"], item["sha256"])
        committed = all_compute_cost(runner.compute_project(project))
        if not math.isfinite(committed) or committed > ceiling:
            raise RecoveryError("failed attempts exceed the unchanged cumulative compute budget")
        next_version = f"v{max([int(row['version'][1:]) for row in previous], default=0) + 1:03d}"
        if not re.fullmatch(r"v[0-9]{3}", next_version):
            raise RecoveryError("primary history version limit reached")
        return {**result, "status": "eligible", "proposal_path": AUTOMATIC_PROPOSAL,
                "plan_sha256": sha(experiment_path(project, 'experiments/plan.json')),
                "budget_sha256": sha(experiment_path(project, 'experiments/budget.json')),
                "version": next_version, "failed_attempt_ids": sorted(row["attempt_id"] for row in rows),
                "diagnostic_evidence": sorted(evidence, key=lambda row: row["path"]),
                "failure_logs": failure_logs,
                "committed_compute_usd": committed, "compute_ceiling_usd": ceiling,
                "cost_accounting_basis": "conservative_plan_estimate_unless_reported_higher",
                "new_analysis_phase": "exploratory", "observed_prior_results": True,
                "scientific_validity_verified": False}
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        return {**result, "status": "blocked", "blocker": str(exc)}


def failure_control_status(project):
    """Distinguish an available native controller step from unknown evidence.

    This never records a retry or makes a model call. It lets the next scheduled
    controller reach automatic_retry instead of pausing on its own old report.
    """
    context = diagnosis_context(project)
    if context["status"] in {"eligible", "not_needed"}:
        return context
    try:
        from scripts import experiment_runner as runner
        from scripts.supplemental_experiments import all_compute_cost
        state = read(project / "state/run.json")
        if (state.get("gate"), state.get("status")) != ("G4", "awaiting_work"):
            return context
        if (project / "state/experiment-execution-lease.json").exists():
            return context
        plan, ceiling = runner.approved_plan(project, experiment_path(project, 'experiments/plan.json'), experiment_path(project, 'experiments/budget.json'))
        rows = records(project)
        failures = [row for row in rows if row.get("status") != "succeeded"]
        requested = 0.0
        for item in failures:
            receipt(project, item)
            _no_start_evidence(project, item)
            attempts = [row for row in rows if row.get("run_id") == item.get("run_id")]
            matches = [row for row in plan["runs"] if row["run_id"] == item.get("run_id")]
            if attempts != [item] or len(matches) != 1:
                return context
            run = matches[0]
            if item.get("approved_plan_sha256") != sha(experiment_path(project, 'experiments/plan.json')):
                return context
            program = run["isolation"].get("engine") if run["isolation"]["kind"] == "container" else run["argv"][0]
            if not shutil.which(program):
                return context
            requested += float(run["estimated_cost_usd"])
        committed = all_compute_cost(runner.compute_project(project))
        if failures and math.isfinite(committed + requested) and committed + requested <= ceiling:
            return {"status": "retry_pending", "paid_calls": 0, "execution_authorized": False}
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        pass
    return context


def automatic_retirement(project, *, run_id):
    """Withdraw failed execution authority after actual current independent audits.

    The next G3 design grants no new budget and must preserve the approved
    thesis/paper topics, prior outcomes, failed outputs and cumulative costs.
    """
    result = {"status": "not_configured", "retired": False, "paid_calls": 0}
    try:
        source = path_in(project, AUTOMATIC_PROPOSAL)
        if not source.is_file():
            return result
        from scripts import output_provenance, review_receipts
        context = diagnosis_context(project)
        if context["status"] == "not_needed":
            return {**result, "status": "not_needed"}
        if context["status"] != "eligible":
            raise RecoveryError(context.get("blocker", "no eligible failed protocol"))
        proposal = read(source)
        origin = output_provenance.current_origin(project, source)
        if origin.get("status") != "tracked" or origin.get("family") != "openai":
            raise RecoveryError("automatic retirement needs the actual authorized non-Claude writer proposal")
        fields = {"schema_version", "operation", "plan_sha256", "budget_sha256", "version", "reason",
                  "prior_outcomes_seen", "observed_prior_results", "new_analysis_phase", "failure_category",
                  "failed_attempt_ids", "diagnostic_evidence"}
        if (set(proposal) != fields or proposal.get("schema_version") != "1.0"
                or proposal.get("operation") != "retire_primary_plan" or proposal.get("prior_outcomes_seen") is not True
                or proposal.get("observed_prior_results") is not True or proposal.get("new_analysis_phase") != "exploratory"
                or proposal.get("failure_category") not in {"implementation_failure", "infrastructure_failure"}
                or any(proposal.get(key) != context[key] for key in (
                    "plan_sha256", "budget_sha256", "version", "failed_attempt_ids", "diagnostic_evidence"))):
            raise RecoveryError("retirement proposal must bind every current failure and explicitly retain observed exploratory results")
        errors = review_receipts.validate_gate(project, "G4")
        if errors:
            raise RecoveryError("; ".join(errors))
        pointer = read(project / "state/review-receipts/G4/latest.json")
        final_path = path_in(project, pointer["path"])
        final = read(final_path)
        if final.get("run_id") != run_id:
            raise RecoveryError("automatic retirement requires this exact writer/critic cycle")
        initial_path = path_in(project, final["initial"]["path"])
        review = [{"path": target.relative_to(project).as_posix(), "sha256": sha(target)} for target in (
            initial_path, path_in(project, read(initial_path)["audit"]["path"]), final_path,
            path_in(project, final["audit"]["path"]))]
        prepared = prepare(project, AUTOMATIC_PROPOSAL, "deterministic_control_plane", "retire_primary_plan")
        authority = {"actor": "deterministic_control_plane", "decision_kind": "automated", "human_confirmation": False,
                     "source_run_id": str(run_id), "source": AUTOMATIC_PROPOSAL, "source_sha256": sha(source),
                     "proposal": proposal, "review_evidence": review,
                     "note": "One bounded automatic withdrawal of a failed protocol after current independent audits; no new execution or budget authorized."}
        _retire(project, prepared, authority)
        manifest = project / HISTORY / proposal["version"] / "manifest.json"
        control = project / CONTROL / "versions" / (proposal["version"] + ".json")
        from scripts.research_artifacts import record
        record(project, [manifest, control, project / "state/run.json"], MODULE)
        return {**result, "status": "retired", "retired": True, "version": proposal["version"],
                "next_gate": "G3", "decision_kind": "automated", "human_confirmation": False}
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        return {**result, "status": "blocked", "blocker": str(exc)}


def prepare(project, source, actor, operation):
    from scripts import experiment_runner as runner
    state = read(project / "state/run.json")
    if state.get("gate") != "G4" or state.get("status") != "awaiting_work":
        raise RecoveryError("primary recovery requires the open G4 stage")
    runner.approved_plan(project, experiment_path(project, 'experiments/plan.json'), experiment_path(project, 'experiments/budget.json'))
    proposal = read(path_in(project, source))
    if (not actor or proposal.get("schema_version") != "1.0" or proposal.get("operation") != operation
            or proposal.get("plan_sha256") != sha(experiment_path(project, 'experiments/plan.json'))
            or proposal.get("budget_sha256") != sha(experiment_path(project, 'experiments/budget.json'))
            or not isinstance(proposal.get("reason"), str) or len(proposal["reason"].strip()) < 20):
        raise RecoveryError("recovery needs an exact plan/budget-bound proposal and substantive reason")
    rows = records(project)
    for item in rows:
        receipt(project, item)
    failed = [r for r in rows if r.get("status") in {"failed", "timed_out"}]
    if not failed:
        raise RecoveryError("primary recovery needs retained failed executor evidence")
    if operation == "approve_primary_retry":
        matches = [r for r in rows if r.get("attempt_id") == proposal.get("failed_attempt_id")]
        if len(matches) != 1 or matches[0] not in failed or proposal.get("failure_category") not in {"infrastructure", "transient_environment"}:
            raise RecoveryError("unchanged retry is only for an inspected infrastructure failure")
        item = matches[0]
        attempts = [r for r in rows if r.get("run_id") == item["run_id"]]
        if (attempts[-1] != item or any(r.get("status") == "succeeded" for r in attempts)
                or (project / CONTROL / "retries" / (item["attempt_id"] + ".json")).exists()
                or not item.get("input_integrity", {}).get("passed")):
            raise RecoveryError("retry must name the latest unchanged failed attempt, once")
        for output in item.get("outputs", []):
            target = path_in(project, output["path"])
            if not target.is_file() or sha(target) != output["sha256"]:
                raise RecoveryError("failed outputs must be preserved before retry authorization")
        return {"proposal": proposal, "failed": item, "next_attempt_number": len(attempts) + 1}
    if operation != "retire_primary_plan":
        raise RecoveryError("unsupported primary recovery operation")
    version = proposal.get("version", "")
    if not re.fullmatch(r"v[0-9]{3}", version) or (project / HISTORY / version).exists():
        raise RecoveryError("choose a new immutable vNNN protocol history version")
    previous_versions = histories(project)
    if previous_versions and version <= previous_versions[-1]["version"]:
        raise RecoveryError("protocol history versions must increase monotonically")
    if proposal.get("prior_outcomes_seen") is not True or proposal.get("new_analysis_phase") not in {"exploratory", "prospective_followup"}:
        raise RecoveryError("amended protocols must disclose observed prior outcomes and the new analysis phase")
    for run in read(experiment_path(project, 'experiments/plan.json'))["runs"]:
        for item in run["inputs"]:
            _original_input(project, item["path"], item["sha256"])
    for prereg in (project / "papers").glob("P[0-9][0-9]/preregistration.json"):
        for item in read(prereg).get("files", []):
            _original_input(project, item["path"], item["sha256"])
    for item in rows:
        for output in item.get("outputs", []):
            _retained_output(project, item, output)
    return {"proposal": proposal, "state": state, "rows": rows}


def apply(project, source, actor, operation, review_sha256, run_id, note):
    prepared = prepare(project, source, actor, operation)
    proposal = prepared["proposal"]
    authority = {"actor": actor, "cloud_review_sha256": review_sha256, "source_run_id": str(run_id),
                 "note": note, "source": source, "source_sha256": sha(project / source), "proposal": proposal}
    if operation == "approve_primary_retry":
        item = prepared["failed"]
        preserved = []
        for output in item.get("outputs", []):
            relative = f"experiments/recovery-artifacts/{item['attempt_id']}/{output['sha256']}{Path(output['path']).suffix}"
            target = path_in(project, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project / output["path"], target)
            preserved.append({**output, "preserved_path": relative})
        value = {**authority, "plan_sha256": proposal["plan_sha256"],
                 "failed_receipt_sha256": sha(receipt(project, item)),
                 "next_attempt_number": prepared["next_attempt_number"], "preserved_outputs": preserved}
        write(project / CONTROL / "retries" / (item["attempt_id"] + ".json"), value)
        return
    _retire(project, prepared, authority)


def _retire(project, prepared, authority):
    from scripts import experiment_runner as runner
    proposal = prepared["proposal"]
    version = proposal["version"]
    folder = project / HISTORY / version
    plan = read(experiment_path(project, 'experiments/plan.json'))
    frozen = {experiment_path(project,p).relative_to(project).as_posix() for p in ("experiments/plan.json", "experiments/budget.json", "experiments/registry.jsonl", "state/run.json")}
    expected_hashes = {}

    def require_original(relative, expected_hash):
        expected_hash = str(expected_hash).lower()
        _original_input(project, relative, expected_hash)
        if relative in expected_hashes and expected_hashes[relative] != expected_hash:
            raise RecoveryError("original frozen input is missing or changed: " + relative)
        expected_hashes[relative] = expected_hash
        frozen.add(relative)

    from scripts.paper_execution import papers
    preregs = [p for p in (project / "papers").glob("P[0-9][0-9]/preregistration.json") if p.parent.name in papers(project)]
    for path in preregs:
        frozen.add(path.relative_to(project).as_posix())
        for item in read(path).get("files", []):
            require_original(item["path"], item["sha256"])
    for run in plan["runs"]:
        for item in run["inputs"]:
            require_original(item["path"], item["sha256"])
    retained_outputs = []
    for item in prepared["rows"]:
        for output in item.get("outputs", []):
            retained_outputs.append(_retained_output(project, item, output))
        retry = project / CONTROL / "retries" / (item["attempt_id"] + ".json")
        if retry.exists():
            # Freeze the actual reviewed mapping before the current plan changes.
            # Later history validation must not call _approval against a new plan.
            require_original(retry.relative_to(project).as_posix(), sha(retry))
    if authority.get("decision_kind") == "automated":
        require_original(authority["source"], authority["source_sha256"])
        for item in proposal["diagnostic_evidence"]:
            require_original(item["path"], item["sha256"])
    files = []
    for relative in sorted(frozen):
        target = path_in(project, relative)
        if not target.is_file():
            raise RecoveryError("original frozen input is missing")
        # Raw/private files remain in the sealed acquisition store, never copied into public history.
        archived = None
        from scripts.cloud_checkpoint import excluded
        archived_path = f"{HISTORY}/{version}/files/{relative}"
        if not excluded(archived_path):
            archived = archived_path
            copy = project / archived
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target, copy)
        files.append({"path": relative, "sha256": sha(target), "archive": archived})
    manifest = {**authority, "version": version, "files": files,
                "run_ids": [r["run_id"] for r in plan["runs"]],
                "output_paths": [p for r in plan["runs"] for p in r["expected_outputs"]],
                "compute_ceiling_usd": runner.project_compute_ceiling(project, read(experiment_path(project, 'experiments/budget.json'))),
                "cost_usd": sum(runner.accounted_run_cost(r) for r in prepared["rows"]),
                "attempt_receipts": [{"path": f"experiments/runs/{r['attempt_id']}/run.json", "sha256": sha(receipt(project, r))} for r in prepared["rows"]],
                "retained_outputs": retained_outputs}
    write(folder / "manifest.json", manifest)
    write(project / CONTROL / "versions" / (version + ".json"), {"manifest_sha256": sha(folder / "manifest.json")})
    # This owner decision withdraws old execution authority; it grants no new execution authority.
    state = prepared["state"]
    from scripts.paper_execution import enabled,selected
    if enabled(project):
        retired_gates={f"{gate}:{selected(project)}" for gate in ("G3","G4","G5")}
        state["approved_gates"]=[g for g in state.get("approved_gates",[]) if g not in retired_gates]
    else:
        state["approved_gates"] = [g for g in state.get("approved_gates", []) if g not in {"G3", "G4"} and not g.startswith("G5")]
    state.update(stage_index=3, stage="experiment-design", gate="G3", status="awaiting_work")
    for key in ("ready_gate", "ready_artifact_sha256"):
        state.pop(key, None)
    state.setdefault("history", []).append({"event": "primary_protocol_retired", "version": version,
        **{key: value for key, value in authority.items() if key in {
            "actor", "source_run_id", "cloud_review_sha256", "decision_kind", "human_confirmation"}}})
    write(project / "state/run.json", state)
    (experiment_path(project, 'experiments/registry.jsonl')).write_text("", encoding="utf-8")
    for path in preregs:
        path.unlink()


def histories(project):
    values = []
    controls = project / CONTROL / "versions"
    for control in sorted(controls.glob("v[0-9][0-9][0-9].json")):
        manifest = project / HISTORY / control.stem / "manifest.json"
        if sha(manifest) != read(control)["manifest_sha256"]:
            raise RecoveryError("retired primary protocol seal changed")
        value = read(manifest)
        if value.get("version") != control.stem:
            raise RecoveryError("retired primary protocol version changed")
        if value.get("decision_kind") == "automated":
            from scripts.output_provenance import current_origin
            from scripts import review_receipts
            for target in (manifest, control):
                origin = current_origin(project, target)
                if (origin.get("status") != "tracked" or origin.get("provider") != "deterministic-control-plane"
                        or origin.get("model") != MODULE):
                    raise RecoveryError("automatic retired protocol seal lacks controller provenance")
            if (value.get("actor") != "deterministic_control_plane" or value.get("human_confirmation") is not False
                    or value.get("proposal", {}).get("observed_prior_results") is not True
                    or value.get("proposal", {}).get("new_analysis_phase") != "exploratory"
                    or not isinstance(value.get("review_evidence"), list) or len(value["review_evidence"]) != 4):
                raise RecoveryError("automatic retired protocol lost its honest decision or analysis phase")
            for item in value.get("review_evidence", []):
                target = path_in(project, item["path"])
                review_receipts._owned(project, target)
                if sha(target) != item["sha256"]:
                    raise RecoveryError("original independent retirement review changed")
        for row in value["files"]:
            if row["archive"] and sha(path_in(project, row["archive"])) != row["sha256"]:
                raise RecoveryError("retired primary protocol archive changed")
        for row in value["attempt_receipts"]:
            if sha(path_in(project, row["path"])) != row["sha256"]:
                raise RecoveryError("retired executor evidence changed")
        for row in value["retained_outputs"]:
            if sha(path_in(project, row["path"])) != row["sha256"]:
                raise RecoveryError("retired executor output changed")
        values.append(value)
    return values


def historical_cost(project):
    return sum(v["cost_usd"] for v in histories(project))


def gate_errors(project, gate, paper_id=None):
    if gate not in {"G3", "G4", "G5"}:
        return []
    try:
        versions = histories(project)
        if not versions:
            return []
        plan, budget = read(experiment_path(project, 'experiments/plan.json')), read(experiment_path(project, 'experiments/budget.json'))
        retired_runs = {r for v in versions for r in v["run_ids"]}
        retired_outputs = {p for v in versions for p in v["output_paths"]}
        if any(r["run_id"] in retired_runs or set(r["expected_outputs"]) & retired_outputs for r in plan["runs"]):
            raise RecoveryError("amended primary plans require new run IDs and distinct output paths")
        from scripts.experiment_runner import budget_ceiling
        budget_ceiling(budget)  # Frozen protocol shape, not another spending cap.
        phase = "exploratory" if versions[-1]["proposal"]["new_analysis_phase"] == "exploratory" else "confirmatory"
        for paper in {r["paper_id"] for r in plan["runs"]}:
            if paper_id and paper != paper_id:
                continue
            from scripts import study_routes
            route = study_routes.route(project, paper)
            if route == "empirical":
                protocol = read(project / "papers" / paper / "experiment-evidence-plan.json")
                phases = {c["analysis_phase"] for c in protocol["comparisons"]}
            elif route == "meta_analysis":
                protocol = read(study_routes.protocol_path(project, paper))
                phases = {o["analysis_phase"] for o in protocol["outcomes"]}
            else:
                phases = {phase}  # Formal proof checks are not empirical confirmatory tests.
            if phases != {phase}:
                raise RecoveryError("amended analyses must retain their reviewed exploratory/prospective phase")
        return []
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return ["primary recovery: " + str(exc)]


def approved_exploration(project):
    versions = histories(project)
    return bool(versions and versions[-1]["proposal"]["new_analysis_phase"] == "exploratory"
                and not gate_errors(project, "G3"))
