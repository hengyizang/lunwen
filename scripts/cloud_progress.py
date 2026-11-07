"""Record actual activity and stop repeated work that has no new inputs."""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

from scripts import researchctl

FILE = "state/continuation-progress.json"
MAX_CONTROL_CYCLES = 12
MAX_STALLED_CYCLES = 2


try:
    from scripts.research_artifacts import read_optional as read
except ImportError:
    from research_artifacts import read_optional as read


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def human_inputs(project: Path) -> str:
    # Only owner/control-plane files reset a paused control attempt. Draft
    # timestamps and audit wording do not establish new scientific evidence.
    paths = ["state/run.json", "state/data-authorizations.json", "state/human-inputs.json"]
    return digest({p: read(project / p) for p in paths})


def work_inputs(project: Path) -> str:
    """Bind concrete next-work inputs, excluding review prose and billing clocks."""
    from scripts.research_artifacts import sha
    from scripts.paper_execution import primary_registry_paths
    paths = [project / "experiments/plan.json", project / "evidence/datasets.jsonl",
             project / "program/literature-search-plan.json",
             project / "program/literature-workbench.json"]
    paths.extend((project / "experiments/papers").glob("P[0-9][0-9]/plan.json"))
    paths.extend((project / "papers").glob("P[0-9][0-9]/preregistration.json"))
    paths.extend(primary_registry_paths(project))

    def fingerprint(path):
        if path.suffix == ".json":
            try:
                return digest(read(path))
            except (ValueError, UnicodeDecodeError):
                pass  # Retain unreadable/invalid input identity for diagnosis.
        return sha(path)

    return digest({p.relative_to(project).as_posix(): fingerprint(p)
                   for p in sorted(set(paths)) if p.is_file() and not p.is_symlink()})


def experiment_attempts(project: Path) -> list[dict]:
    """Read native receipts, including attempts archived during this cycle."""
    from scripts.paper_execution import primary_registry_paths
    from scripts import research_phase, primary_recovery
    from scripts.research_artifacts import path_in, sha
    attempts = {}

    def add(scope, item, actual, original=None):
        if read(actual) != item:
            raise ValueError("experiment registry differs from its actual receipt")
        fingerprint = sha(actual)
        attempts[fingerprint] = {"attempt_id": item["attempt_id"], "paper_id": item.get("paper_id"),
            "status": item.get("status"), "receipt_path": actual.relative_to(project).as_posix(),
            "receipt_sha256": fingerprint, "scope_path": scope.relative_to(project).as_posix(),
            "original_receipt_path": (scope / original).relative_to(project).as_posix() if original else actual.relative_to(project).as_posix()}

    def registry(scope, path, mapping=None):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            attempt_id = item.get("attempt_id")
            if not isinstance(attempt_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", attempt_id):
                raise ValueError("experiment receipt needs its actual attempt ID")
            relative = "experiments/runs/" + attempt_id + "/run.json"
            actual = path_in(scope, (mapping or {}).get(relative, relative))
            add(scope, item, actual, relative)

    scopes = [project, *sorted((project / "experiments/supplemental").glob("P[0-9][0-9]/[RI][0-9][0-9][0-9]/s[0-9][0-9][0-9]"))]
    for scope in scopes:
        for path in primary_registry_paths(scope):
            registry(scope, path)
        for archive in research_phase.histories(scope):
            registry(scope, path_in(scope, archive["registry_path"]),
                     {row["source"]: row["archive_path"] for row in archive["files"]})
        for archive in primary_recovery.histories(scope):
            for binding in archive["attempt_receipts"]:
                actual = path_in(scope, binding["path"])
                add(scope, read(actual), actual)
    return list(attempts.values())


def _amount(value):
    return float(value) if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def decision_resources(project: Path, decision: dict, before: dict, after: dict, *, cycle_ids=None) -> dict:
    """Join actual cycle/attempt receipts; unknown billing is never reported as free."""
    from scripts import model_runtime, model_spend
    from scripts.experiment_runner import accounted_run_cost, ExperimentError
    from scripts.research_artifacts import path_in, sha
    cycles = sorted(set(cycle_ids if cycle_ids is not None else [decision.get("cycle_id")]) - {None})
    cycle = decision.get("cycle_id") if decision.get("cycle_id") in cycles else (cycles[0] if len(cycles) == 1 else None)
    result = {"cycle_id": cycle, "cycle_ids": cycles, "models": {"currency": "CNY", "attempts": []},
              "experiments": {"currency": "USD", "attempts": []}, "unknown": []}
    if not cycles:
        result["unknown"].append("No current scientific cycle is bound; model costs cannot be attributed.")
    ledger = project / "state/model-usage.jsonl"
    rows = [row for row in model_runtime.ledger_entries(project)
            if row.get("run_id") in cycles and not row.get("validation_status")]
    try:
        spend = model_spend.read(project) or {}
    except model_spend.SpendControlError as exc:
        spend = {}
        result["unknown"].append("Model accounting state is unavailable: " + str(exc))
    settled = {row["receipt_id"]: row for row in [*spend.get("settlement_events", []), *spend.get("reconciliation_events", [])]}
    for row in rows:
        reservation = row.get("reservation_id")
        event = settled.get(reservation, {})
        pending = spend.get("reservations", {}).get(reservation)
        basis = row.get("billing", {}).get("cost_basis") or row.get("cost_status", "unknown")
        amount = _amount(row.get("cost_cny"))
        kind = "unknown"
        if pending:
            amount, kind = _amount(pending["max_cost_cny"]), "pending_reservation"
        elif _amount(event.get("actual_cost_cny")) is not None:
            amount, kind, basis = _amount(event["actual_cost_cny"]), "verified_charge", event.get("cost_basis", "owner_reconciled")
        elif _amount(event.get("accounted_cost_cny")) is not None:
            amount, kind, basis = _amount(event["accounted_cost_cny"]), "estimated_or_calculated", event.get("cost_basis")
        elif row.get("cache_hit") is True:
            amount, kind, basis = 0.0, "verified_charge", "exact_cache_replay_no_inference"
        elif amount is not None and row.get("cost_status") == "settled_gateway_debit":
            kind = "verified_charge"
        elif amount is not None and row.get("cost_status") in {"settled_usage_receipt", "estimated_upper_bound"}:
            kind = "estimated_or_calculated"
        elif row.get("zero_cost_not_confirmed") or row.get("cost_status") == "accounted_upper_bound":
            amount = _amount(row.get("reserved_cost_cny"))
            kind = "pending_reservation" if amount is not None else "unknown"
        result["models"]["attempts"].append({"cycle_id": row.get("run_id"), "role": row.get("role"), "reservation_id": reservation,
            "status": "failed" if row.get("transport_error_type") else row.get("completion_status", "recorded"),
            "duration_seconds": _amount(row.get("duration_seconds")), "cost_cny": amount,
            "cost_kind": kind, "cost_basis": basis, "ledger_record_sha256": digest(row)})
    recorded_reservations = {row.get("reservation_id") for row in rows}
    for reservation, pending in spend.get("reservations", {}).items():
        if pending.get("run_id") in cycles and reservation not in recorded_reservations:
            result["models"]["attempts"].append({"cycle_id": pending["run_id"], "role": None, "reservation_id": reservation,
                "status": "reservation_without_completed_usage", "duration_seconds": None,
                "cost_cny": _amount(pending["max_cost_cny"]), "cost_kind": "pending_reservation",
                "cost_basis": "unresolved_control_reservation"})
    model = result["models"]
    model.update(known_duration_seconds=round(sum(row["duration_seconds"] or 0 for row in model["attempts"]), 6) if any(row["duration_seconds"] is not None for row in model["attempts"]) else None,
        duration_unknown_attempts=sum(row["duration_seconds"] is None for row in model["attempts"]),
        cost_totals_cny={kind: round(sum(row["cost_cny"] or 0 for row in model["attempts"] if row["cost_kind"] == kind), 8)
                         for kind in ("verified_charge", "estimated_or_calculated", "pending_reservation")},
        cost_unknown_attempts=sum(row["cost_kind"] == "unknown" for row in model["attempts"]))
    model["sources"] = [{"path": path.relative_to(project).as_posix(), "sha256": sha(path)}
                        for path in (ledger, project / model_spend.FILE) if path.is_file()]
    if not rows:
        result["unknown"].append("No API usage rows match this cycle; absent usage is not zero cost.")
    for path in sorted((project / "state/runs").glob("*/journal.json")):
        journal = read(path)
        if journal.get("run_id") not in {item + "-" + str(journal.get("stage")) for item in cycles}:
            continue
        duration = None
        try:
            duration = _amount((datetime.fromisoformat(journal["finished_at"]) - datetime.fromisoformat(journal["started_at"])).total_seconds())
        except (KeyError, ValueError, TypeError):
            pass
        result["cli"] = {"duration_seconds": duration, "cost": None, "currency": None,
            "cost_status": "subscription_spend_not_measured", "source": {"path": path.relative_to(project).as_posix(), "sha256": sha(path)}}
        result["unknown"].append("CLI subscription charges are not measured by the API ledger.")
    prior = {row["receipt_sha256"] for row in before.get("experiment_attempts", [])}
    sources = {(source["path"], source["sha256"]) for item in decision.get("decisions", []) for source in item["sources"]}
    for descriptor in after.get("experiment_attempts", []):
        path = path_in(project, descriptor["receipt_path"])
        if sha(path) != descriptor["receipt_sha256"]:
            raise ValueError("decision resource receipt changed after snapshot")
        item = read(path)
        scope = project / descriptor.get("scope_path", ".")
        bindings = {(descriptor["receipt_path"], descriptor["receipt_sha256"]),
                    (descriptor.get("original_receipt_path", descriptor["receipt_path"]), descriptor["receipt_sha256"])}
        bindings.update(((scope / row["path"]).relative_to(project).as_posix(), row["sha256"]) for row in item.get("outputs", []))
        fresh = descriptor["receipt_sha256"] not in prior
        if not fresh and not sources.intersection(bindings):
            continue
        try:
            accounted = accounted_run_cost(item)
        except ExperimentError:
            accounted = None
        result["experiments"]["attempts"].append({**descriptor, "association": "new_this_cycle" if fresh else "cited_prior_evidence",
            "duration_seconds": _amount(item.get("runtime_seconds")), "accounted_cost_usd": accounted,
            "reported_cost_usd": _amount(item.get("reported_cost_usd")),
            "cost_basis": "reported_and_conservative_plan_maximum" if item.get("reported_cost_usd") is not None else "conservative_plan_estimate"})
    for association in ("new_this_cycle", "cited_prior_evidence"):
        attempts = [row for row in result["experiments"]["attempts"] if row["association"] == association]
        result["experiments"][association] = {"attempt_count": len(attempts),
            "known_duration_seconds": round(sum(row["duration_seconds"] or 0 for row in attempts), 6),
            "duration_unknown_attempts": sum(row["duration_seconds"] is None for row in attempts),
            "accounted_cost_usd": round(sum(row["accounted_cost_usd"] or 0 for row in attempts), 8),
            "accounted_cost_unknown_attempts": sum(row["accounted_cost_usd"] is None for row in attempts),
            "known_reported_cost_usd": round(sum(row["reported_cost_usd"] or 0 for row in attempts), 8),
            "actual_cost_unknown_attempts": sum(row["reported_cost_usd"] is None for row in attempts)}
    return result


def resource_snapshot(project: Path) -> dict:
    """Bound subsequent usage without duplicating the historical billing ledger."""
    from scripts import model_runtime, model_spend
    rows = model_runtime.ledger_entries(project)
    try:
        control = model_spend.read(project) or {}
    except model_spend.SpendControlError:
        control = {}  # The resource report retains the accounting-state error.
    journal = read(project / "state/autopilot.json", {})
    return {"usage_count": len(rows), "usage_sha256": digest(rows),
            "reservations": {key: row.get("run_id") for key, row in control.get("reservations", {}).items()},
            "cli": {"run_id": journal.get("run_id"), "stage": journal.get("stage"), "sha256": digest(journal)}}


def snapshot(slug: str) -> dict:
    project = researchctl.project_dir(slug)
    state = researchctl.load_state(slug)
    errors = researchctl.gate_errors(slug, state["gate"]) if state["gate"] else []
    errors = sorted(set(re.sub(r"\d{8}T\d+Z", "<run>", str(e).replace(str(project), "<project>")) for e in errors))
    # Executed activity is distinct from a scientific conclusion. Keep failed
    # attempts too; arbitrary manuscript bytes never establish research progress.
    receipts = []
    attempts = experiment_attempts(project)
    receipts.extend(row["receipt_sha256"] for row in attempts)
    paths=[project/"evidence/literature-api-ledger.jsonl"]
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines() if path.is_file() else []:
            item = json.loads(line)
            if item.get("status") in {"success", "succeeded"}:
                receipts.append(item.get("response_sha256") or digest(item.get("outputs", [])))
    from scripts import literature_evidence, literature_model_screening
    for item in literature_evidence.read_jsonl(project / "evidence/search-log.jsonl"):
        if str(item.get("screened_by", "")).startswith("model:") and not literature_model_screening.verify(project, item):
            receipts.append(digest({"receipt": item["evidence_receipt_id"], "screened_by": item["screened_by"],
                                    "included": item["included_work_ids"], "excluded": item["exclusion_reasons"]}))
    return {"scope": f"{state['stage']}:{state['active_paper']}", "errors": errors,
            "gate_error_groups": researchctl.summarize_gate_errors(errors),
            "experiment_attempts":attempts,
            "resource_snapshot": resource_snapshot(project),
            "receipts": sorted(set(receipts)), "human_inputs": human_inputs(project),
            "work_inputs": work_inputs(project),
            "notebook_sha256": hashlib.sha256((project/"program/research-notebook.json").read_bytes()).hexdigest()
                if (project/"program/research-notebook.json").is_file() else None}


def external_blockers(project: Path, errors: list[str]) -> list[dict]:
    report = read(project / "state/research-steps.json", {})
    automatic_kinds = {"data_rights_evidence", "data_rights_review", "data_quality_confirmation", "reproduction_confirmation", "figure_visual_review", "literature_screening"}
    blockers = [item for item in report.get("blockers", []) if item.get("kind") not in automatic_kinds]
    if any(item.get("kind") in {"experiment_inspection", "experiment_failure_diagnosis"} for item in blockers):
        from scripts.primary_recovery import failure_control_status
        status = failure_control_status(project)
        if status["status"] in {"eligible", "retry_pending"}:
            blockers = [item for item in blockers if item.get("kind") not in {"experiment_inspection", "experiment_failure_diagnosis"}]
    patterns = {
        "jcr_source_required": ("licensed jcr", "jcr verification", "jcr source"),
    }
    for kind, phrases in patterns.items():
        matches = [e for e in errors if any(p in e.casefold() for p in phrases)]
        if matches:
            blockers.append({"kind": kind, "requirements": matches[:8]})
    return blockers


def record(slug: str, before: dict, run_id: str, exit_code: int) -> dict:
    project = researchctl.project_dir(slug)
    after = snapshot(slug)
    old = read(project / FILE, {})
    if old.get("scope") != after["scope"] or old.get("human_inputs") != after["human_inputs"]:
        old = {}
    elif old.get("work_inputs") is not None and old["work_inputs"] != before.get("work_inputs"):
        old = {**old, "stalled_cycles": 0, "control_cycles": 0}
    report = read(project / "state/research-steps.json", {})
    paid = report.get("paid_model_cycle") is True
    reduced = set(after["errors"]) < set(before["errors"])
    evidence_added = bool(set(after["receipts"]) - set(before["receipts"]))
    inputs_changed = before.get("work_inputs") is not None and before["work_inputs"] != after["work_inputs"]
    progressed = reduced or evidence_added or inputs_changed
    from scripts.research_notebook import cycle_assessment
    prior_stage, prior_paper = before["scope"].split(":", 1)
    from scripts.model_runtime import ledger_entries
    baseline, current = before.get("resource_snapshot", {}), after["resource_snapshot"]
    rows, cycles, binding_errors = ledger_entries(project), set(), []
    if baseline:
        count = baseline["usage_count"]
        if digest(rows[:count]) != baseline["usage_sha256"]:
            binding_errors.append("The prior usage ledger changed; this invocation cannot be isolated.")
        else:
            cycles.update(row.get("run_id") for row in rows[count:] if not row.get("validation_status"))
        cycles.update(value for key, value in current["reservations"].items() if key not in baseline["reservations"])
        cli = current["cli"]
        suffix = "-" + str(cli.get("stage"))
        if cli != baseline["cli"] and isinstance(cli.get("run_id"), str) and cli["run_id"].endswith(suffix):
            cycles.add(cli["run_id"][:-len(suffix)])
    cycles = {value for value in cycles if isinstance(value, str) and value}
    bound_cycle = next(iter(cycles)) if len(cycles) == 1 else None
    decision = cycle_assessment(project, prior_stage, bound_cycle, paper_id=prior_paper)
    if binding_errors or (cycles and decision.get("cycle_id") not in cycles) or (exit_code and not cycles):
        decision = {"status": "pending", "cycle_id": bound_cycle, "decisions": [],
                    "errors": binding_errors or ["This invocation has no current independently reviewed scientific decision."],
                    "scientific_completion_verified": False}
    decision["resource_use"] = decision_resources(project, decision, before, after,
        cycle_ids=[] if binding_errors else cycles)
    decision["resource_use"]["unknown"].extend(binding_errors)
    semantic = None
    if decision["status"] in {"independently_observed", "independently_reviewed", "historically_reviewed"} and decision["notebook"]["sha256"] != before.get("notebook_sha256"):
        semantic = {"status": decision["status"] + "_decision", "cycle_id": decision["cycle_id"],
                    "assessment_scope": decision.get("assessment_scope", "current_scientific_inputs"),
                    "outcomes": [{"question_id": row["question_id"], "decision_id": row["id"], "outcome": row["outcome"],
                        "decision": row["decision"], "sources": row["sources"]} for row in decision["decisions"]],
                    "independent_review": decision["independent_review"], "scientific_gain_verified": False}
    value = {"schema_version": "1.0", **after, "source_run_id": str(run_id),
             "last_exit_code": exit_code, "model_cycles": old.get("model_cycles", 0) + int(paid),
             "control_cycles": 0 if progressed else old.get("control_cycles", 0) + int(not paid),
             "stalled_cycles": 0 if progressed else old.get("stalled_cycles", 0) + int(paid),
             "control_progress": progressed, "new_work_inputs": inputs_changed,
             "semantic_progress": semantic,"scientific_progress_verified":False,
             "research_decision": decision,
             "new_experiment_attempts":len({row["receipt_sha256"] for row in after["experiment_attempts"]}
                                           - {row["receipt_sha256"] for row in before.get("experiment_attempts",[])}),
             "external_blockers": external_blockers(project, after["errors"])}
    researchctl.write_json(project / FILE, value)
    return value


def pause_reason(slug: str) -> dict | None:
    project = researchctl.project_dir(slug)
    value = read(project / FILE, {})
    state = researchctl.load_state(slug)
    if (value.get("scope") != f"{state['stage']}:{state['active_paper']}"
            or value.get("human_inputs") != human_inputs(project)):
        return None
    current_errors = researchctl.gate_errors(slug, state["gate"]) if state.get("gate") else []
    current_external = external_blockers(project, current_errors)
    if current_external:
        return {"reason": "external_input_required", "blockers": current_external}
    if value.get("control_cycles", 0) >= MAX_CONTROL_CYCLES:
        return {"reason": "control_retry_limit", "attempts": value["control_cycles"], "limit": MAX_CONTROL_CYCLES}
    if value.get("stalled_cycles", 0) >= MAX_STALLED_CYCLES:
        current = snapshot(slug)
        changed = (bool(set(current["receipts"]) - set(value.get("receipts", [])))
                   or set(current["errors"]) < set(value.get("errors", []))
                   or (value.get("work_inputs") is not None
                       and current["work_inputs"] != value["work_inputs"]))
        if not changed:
            return {"reason": "no_new_research_inputs", "attempts": value["stalled_cycles"],
                    "limit": MAX_STALLED_CYCLES,
                    "next_action": "Supply a new source, result or revised experiment/query plan; a clock wakeup or rephrased draft does not restart work."}
    return None


def resume(slug: str, expected_sha256: str, actor: str, note: str, run_id: str) -> None:
    """Owner-reviewed repair only; does not grant money or any scientific gate."""
    from scripts.cloud_continuation import STATUS
    project = researchctl.project_dir(slug)
    status = project / STATUS
    if (not status.is_file() or hashlib.sha256(status.read_bytes()).hexdigest() != expected_sha256
            or not actor.strip() or not 10 <= len(note.strip()) <= 500):
        raise ValueError("resume requires the exact reviewed status hash, actor and repair note")
    history = project / "state/continuation-resumes.jsonl"
    event = {"actor": actor, "note": note, "run_id": str(run_id), "status_sha256": expected_sha256,
             "previous_status": read(status), "previous_progress": read(project / FILE)}
    with history.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    researchctl.write_json(status, {"schema_version": "1.0", "last_cycle_exit_code": 0,
                                   "reason": "owner_inspected_repair", "source_run_id": str(run_id)})
    (project / FILE).unlink(missing_ok=True)
