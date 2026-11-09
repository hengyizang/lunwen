"""Record actual activity and stop repeated work that has no new inputs."""
from __future__ import annotations

import hashlib
import json
import math
import re
from functools import wraps
from datetime import datetime
from pathlib import Path

from scripts import researchctl

FILE = "state/continuation-progress.json"
MAX_CONTROL_CYCLES = 12
MAX_STALLED_CYCLES = 2
FINGERPRINT_VERSION = 3
INPUT_KEYS = ("human_inputs", "work_inputs", "receipts")
RESUMES = "state/continuation-resumes.jsonl"


try:
    from scripts.research_artifacts import read_optional as read
except ImportError:
    from research_artifacts import read_optional as read


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def research_input(value, relative=""):
    """Remove only the named config's top-level administrative clock fields.

    Scientific timestamps, strings and execution queues retain their exact
    values and ordering; JSON serialization itself is normalized by digest().
    """
    if isinstance(value, dict) and relative in {
            "program/literature-search-plan.json", "program/literature-workbench.json"}:
        return {key: item for key, item in value.items()
                if key not in {"generated_at", "updated_at", "refreshed_at", "last_checked_at"}}
    return value


def human_inputs(project: Path) -> str:
    # Stage/history timestamps and machine status updates are not owner decisions.
    state = read(project / "state/run.json", {})
    return digest(research_input({"topic_decisions": [row for row in state.get("approvals", [])
        if row.get("gate") in {"G1", "G2"}], **{p: read(project / p) for p in (
            "state/data-authorizations.json", "state/human-inputs.json")}}))


def work_inputs(project: Path) -> str:
    """Bind next-work inputs, excluding attempt IDs, review prose and billing clocks."""
    from scripts.research_artifacts import sha
    paths = [project / "experiments/plan.json", project / "evidence/datasets.jsonl",
             project / "program/literature-search-plan.json", project / "program/literature-workbench.json"]
    paths.append(project / "program/hypothesis-register.json")
    paths.extend((project / "experiments/papers").glob("P[0-9][0-9]/plan.json"))
    paths.extend((project / "papers").glob("P[0-9][0-9]/preregistration.json"))

    def fingerprint(path):
        try:
            if path.suffix == ".json":
                return digest(research_input(read(path), path.relative_to(project).as_posix()))
            if path.suffix == ".jsonl":
                return digest([json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])
        except (ValueError, UnicodeDecodeError):
            pass  # Invalid inputs remain distinguishable for diagnosis.
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


def unsent_requests(control):
    """Only native cancellation events can prove a generation was never sent."""
    events = control.get("unsent_events", [])
    excluded = set(control.get("reservations", {})) | {
        row.get("receipt_id") for row in [*control.get("settlement_events", []), *control.get("reconciliation_events", [])]}
    result, seen = {}, set()
    for event in events:
        if not isinstance(event, dict):
            continue
        receipt, reservation = event.get("receipt_id"), event.get("reservation", {})
        if not isinstance(receipt, str) or not isinstance(reservation, dict):
            continue
        if receipt in seen:  # Ambiguous cancellation histories never prove zero cost.
            excluded.add(receipt)
        seen.add(receipt)
        if (event.get("generation_sent") is False and isinstance(reservation.get("run_id"), str)
                and reservation["run_id"].strip() and isinstance(event.get("reason"), str) and event["reason"].strip()
                and _amount(reservation.get("max_cost_cny")) is not None):
            result[receipt] = reservation["run_id"]
    return {(receipt, run) for receipt, run in result.items() if receipt not in excluded}


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
    unsent = unsent_requests(spend)
    for row in rows:
        reservation = row.get("reservation_id")
        event = settled.get(reservation, {})
        pending = spend.get("reservations", {}).get(reservation)
        basis = row.get("billing", {}).get("cost_basis") or row.get("cost_status", "unknown")
        amount = _amount(row.get("cost_cny"))
        kind = "unknown"
        not_sent = (reservation, row.get("run_id")) in unsent
        if not_sent:
            amount, kind, basis = 0.0, "confirmed_not_sent", "controller_confirmed_generation_not_sent"
        elif pending:
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
            "status": "not_sent" if not_sent else "failed" if row.get("transport_error_type") else row.get("completion_status", "recorded"),
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


def snapshot(slug: str | Path) -> dict:
    # Explicit project paths also serve the API adapter; gate diagnostics belong
    # to the cloud controller and never determine whether science progressed.
    project = slug if isinstance(slug, Path) else researchctl.project_dir(slug)
    state = read(project / "state/run.json")
    errors = researchctl.gate_errors(slug, state["gate"]) if isinstance(slug, str) and state.get("gate") else []
    errors = sorted(set(re.sub(r"\d{8}T\d+Z", "<run>", str(e).replace(str(project), "<project>")) for e in errors))
    # Executed activity is distinct from a scientific conclusion. Keep failed
    # attempts too; arbitrary manuscript bytes never establish research progress.
    receipts = []
    attempts = experiment_attempts(project)
    for row in attempts:
        receipt = read(project / row["receipt_path"])
        # No-start, failed transport and new attempt IDs remain activity; only
        # actual registered outputs supply new material for scientific work.
        receipts.extend(digest(output) for output in receipt.get("outputs", []))
    from scripts import literature_evidence, literature_model_screening
    sources = {}
    for item in literature_evidence.read_jsonl(project / "evidence/literature-api-ledger.jsonl"):
        if item.get("status") not in {"success", "succeeded"}:
            continue
        from scripts.research_artifacts import path_in, sha
        target = path_in(project, item["normalized_results_path"])
        if sha(target) != item["normalized_results_sha256"]:
            raise ValueError("literature result changed after its receipt")
        sources[item.get("receipt_id")] = digest(research_input(read(target)))
        receipts.append(sources[item.get("receipt_id")])
    for item in literature_evidence.read_jsonl(project / "evidence/search-log.jsonl"):
        if str(item.get("screened_by", "")).startswith("model:") and not literature_model_screening.verify(project, item):
            selected = {"source": sources[item["evidence_receipt_id"]],
                        "included": sorted(item["included_work_ids"])}
            receipts.append(digest(selected))
    return {"input_fingerprint_version": FINGERPRINT_VERSION,
            "scope": f"{state['stage']}:{state.get('active_paper')}", "errors": errors,
            "gate_error_groups": researchctl.summarize_gate_errors(errors),
            "experiment_attempts":attempts,
            "resource_snapshot": resource_snapshot(project),
            "receipts": sorted(set(receipts)), "human_inputs": human_inputs(project),
            "work_inputs": work_inputs(project),
            "notebook_sha256": hashlib.sha256((project/"program/research-notebook.json").read_bytes()).hexdigest()
                if (project/"program/research-notebook.json").is_file() else None}


def saved_progress(project, *, record_baseline=False):
    """Opaque earlier fingerprints cannot establish a new input or approval.

    Queries stay read-only. The next existing cycle/control mutation may bind a
    baseline in the resume history, preserving the original checkpoint and pause.
    Subsequent changes can then be compared without guessing historical inputs.
    """
    value = read(project / FILE, {})
    if not value.get("scope") or value.get("input_fingerprint_version") == FINGERPRINT_VERSION:
        return value
    from scripts.research_artifacts import sha
    source_hash = sha(project / FILE)
    history = project / RESUMES
    events = [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines() if line.strip()] if history.is_file() else []
    bound = next((event for event in events if event.get("event") == "fingerprint_baseline"
                  and event.get("checkpoint_sha256") == source_hash
                  and event.get("input_fingerprint_version") == FINGERPRINT_VERSION), None)
    current = snapshot(project) if not bound else bound["baseline"]
    baseline = {key: current[key] for key in INPUT_KEYS}
    if record_baseline and not bound:
        with history.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": "fingerprint_baseline", "checkpoint_sha256": source_hash,
                "input_fingerprint_version": FINGERPRINT_VERSION, "baseline": baseline,
                "previous_progress": value, "grants_retry": False}, ensure_ascii=False) + "\n")
    return {**value, **baseline, "input_comparison": "bound_compatibility_baseline" if bound or record_baseline
            else "legacy_fingerprints_incomparable_until_control_baseline"}


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


def record(slug: str | Path, before: dict, run_id: str | None, exit_code: int) -> dict:
    project = slug if isinstance(slug, Path) else researchctl.project_dir(slug)
    after = snapshot(slug)
    previous = old = saved_progress(project, record_baseline=True)
    if before.get("input_fingerprint_version") != FINGERPRINT_VERSION:
        before = {**before, **{key: previous.get(key, after[key]) for key in INPUT_KEYS}}
    if old.get("scope") != after["scope"] or old.get("human_inputs") != after["human_inputs"]:
        old = {}
    elif ((old.get("work_inputs") is not None and old["work_inputs"] != before.get("work_inputs"))
          or set(before.get("receipts", [])) - set(old.get("receipts", []))):
        old = {**old, "stalled_cycles": 0, "control_cycles": 0}
    reduced = set(after["errors"]) < set(before["errors"])
    evidence_added = bool(set(after["receipts"]) - set(before["receipts"]))
    inputs_changed = before.get("work_inputs") is not None and before["work_inputs"] != after["work_inputs"]
    progressed = evidence_added or inputs_changed
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
    accounted = previous.get("resource_snapshot") or baseline
    count = accounted.get("usage_count", 0)
    from scripts import model_spend
    unsent = unsent_requests(model_spend.read(project) or {})
    paid_cycles = {row.get("run_id") for row in rows[count:]
                   if not row.get("validation_status") and row.get("cache_hit") is not True
                   and (row.get("reservation_id"), row.get("run_id")) not in unsent}
    paid_cycles.update(value for key, value in current["reservations"].items()
                       if key not in accounted.get("reservations", {}))
    paid_cycles.discard(None)
    paid = len(paid_cycles)
    # API and cloud checkpoint observe the same ledger; never charge its cycle
    # twice. A failed call counts even when no writer/manifest was produced.
    already_recorded = baseline != current and previous.get("resource_snapshot") == current
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
    value = {"schema_version": "1.0", **after, "source_run_id": str(run_id) if run_id is not None else bound_cycle,
             "last_exit_code": exit_code, "model_cycles": old.get("model_cycles", 0) + paid,
             "control_cycles": 0 if progressed else old.get("control_cycles", 0) + int(not paid and not already_recorded),
             "stalled_cycles": 0 if progressed else old.get("stalled_cycles", 0) + paid,
             "control_progress": progressed or reduced, "new_work_inputs": inputs_changed,
             "semantic_progress": semantic,"scientific_progress_verified":False,
             "research_decision": decision,
             "new_experiment_attempts":len({row["receipt_sha256"] for row in after["experiment_attempts"]}
                                           - {row["receipt_sha256"] for row in before.get("experiment_attempts",[])}),
             "external_blockers": external_blockers(project, after["errors"])}
    researchctl.write_json(project / FILE, value)
    return value


def pause_reason(slug: str | Path) -> dict | None:
    project = slug if isinstance(slug, Path) else researchctl.project_dir(slug)
    value = saved_progress(project)
    state = read(project / "state/run.json")
    if (value.get("scope") != f"{state['stage']}:{state.get('active_paper')}"
            or value.get("human_inputs") != human_inputs(project)):
        return None
    current_errors = researchctl.gate_errors(slug, state["gate"]) if isinstance(slug, str) and state.get("gate") else []
    current_external = external_blockers(project, current_errors)
    if current_external:
        return {"reason": "external_input_required", "blockers": current_external}
    if (value.get("control_cycles", 0) >= MAX_CONTROL_CYCLES
            or value.get("stalled_cycles", 0) >= MAX_STALLED_CYCLES):
        current = snapshot(slug)
        changed = (bool(set(current["receipts"]) - set(value.get("receipts", [])))
                   or (value.get("work_inputs") is not None and current["work_inputs"] != value["work_inputs"]))
        if not changed:
            if value.get("control_cycles", 0) >= MAX_CONTROL_CYCLES:
                return {"reason": "control_retry_limit", "attempts": value["control_cycles"], "limit": MAX_CONTROL_CYCLES}
            return {"reason": "no_new_research_inputs", "attempts": value["stalled_cycles"],
                    **({"input_comparison": value["input_comparison"]} if "input_comparison" in value else {}),
                    "limit": MAX_STALLED_CYCLES,
                    "next_action": "Supply a new source, result or revised experiment/query plan; a clock wakeup or rephrased draft does not restart work."}
    return None


def track_cycle(resolve_project):
    """Track the sole API execution chain, including exceptions before its writer."""
    def decorate(function):
        @wraps(function)
        def tracked(slug, *args, **kwargs):
            project = resolve_project(slug)
            if not (project / "state/run.json").is_file():
                return function(slug, *args, **kwargs)  # Preserve native initialization errors.
            pending = read(project / FILE, {}).get("pending_cycle")
            if pending:
                record(project, pending, None, 1)
            saved_progress(project, record_baseline=True)
            pause = pause_reason(project)
            if pause:
                raise ValueError("Research continuation paused: " + pause["reason"])
            before = snapshot(project)
            researchctl.write_json(project / FILE, {**read(project / FILE, {}), "pending_cycle": before})
            exit_code = 1
            try:
                result = function(slug, *args, **kwargs)
                exit_code = 0
                return result
            finally:
                record(project, before, None, exit_code)
        return tracked
    return decorate


def resume(slug: str, expected_sha256: str, actor: str, note: str, run_id: str) -> None:
    """Owner-reviewed repair only; does not grant money or any scientific gate."""
    from scripts.cloud_continuation import STATUS
    project = researchctl.project_dir(slug)
    status = project / STATUS
    if (not status.is_file() or hashlib.sha256(status.read_bytes()).hexdigest() != expected_sha256
            or not actor.strip() or not 10 <= len(note.strip()) <= 500):
        raise ValueError("resume requires the exact reviewed status hash, actor and repair note")
    history = project / RESUMES
    event = {"actor": actor, "note": note, "run_id": str(run_id), "status_sha256": expected_sha256,
             "previous_status": read(status), "previous_progress": read(project / FILE)}
    with history.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    researchctl.write_json(status, {"schema_version": "1.0", "last_cycle_exit_code": 0,
                                   "reason": "owner_inspected_repair", "source_run_id": str(run_id)})
    (project / FILE).unlink(missing_ok=True)
