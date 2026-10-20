"""Summarize frozen blinded judgments and recorded costs without certifying quality."""
from __future__ import annotations

import itertools
import json
import math
import statistics
from pathlib import Path
from scripts.research_artifacts import path_in, read, record, sha, write
from scripts import review_packets


def protocol(packet):
    spec = packet.get("analysis")
    if not isinstance(spec, dict):
        raise ValueError("freeze an analysis protocol in the packet before collecting ratings")
    minimum = spec.get("minimum_raters")
    if type(minimum) is not int or not 2 <= minimum <= 20:
        raise ValueError("analysis requires 2-20 named raters")
    dimensions = {r["id"]: r for r in packet["rubric"]["dimensions"]}
    thresholds = spec.get("qualification_thresholds")
    if not isinstance(thresholds, dict) or set(thresholds) != set(dimensions):
        raise ValueError("freeze qualification thresholds for every dimension")
    for key, threshold in thresholds.items():
        if type(threshold) not in {int, float} or not math.isfinite(threshold) or not dimensions[key]["min"] <= threshold <= dimensions[key]["max"]:
            raise ValueError("invalid qualification threshold")
    splits, ownership = {}, {}
    for case in packet["cases"]:
        split = spec.get("case_partitions", {}).get(case["id"])
        if split not in {"calibration", "holdout"}:
            raise ValueError("every case needs a frozen calibration/holdout partition")
        splits[case["id"]] = split
        for source in case["sources"]:
            group = source["sha256"]
            if group in ownership and ownership[group] != split:
                raise ValueError("the same source cannot leak across calibration and holdout")
            ownership[group] = split
    if set(spec["case_partitions"]) != set(splits) or set(splits.values()) != {"calibration", "holdout"}:
        raise ValueError("both partitions and exactly the declared cases are required")
    run_ids = spec.get("cost_run_ids", [])
    if not isinstance(run_ids, list) or any(not isinstance(x, str) or not x for x in run_ids) or len(set(run_ids)) != len(run_ids):
        raise ValueError("cost run IDs must be unique explicit IDs")
    for case in packet["cases"]:
        for candidate in case["candidates"]:
            values = candidate.get("run_ids", [])
            if not isinstance(values, list) or any(not isinstance(x, str) or not x for x in values) or len(set(values)) != len(values):
                raise ValueError("candidate run IDs must be a unique list")
    if not isinstance(spec.get("additional_cost_receipts", []), list) or len(spec.get("additional_cost_receipts", [])) > 200:
        raise ValueError("at most 200 additional cost receipts are permitted")
    return spec


def settled_cost(row):
    """Accept actual scoped charges, never estimates or unreconciled holds."""
    value = row.get("cost_cny")
    if (type(value) not in {int, float} or not math.isfinite(value) or value < 0
            or row.get("usage_estimated") is True):
        return None
    status = row.get("cost_status")
    if status == "settled_usage_receipt" or (status is None and row.get("cache_hit") is True and value == 0):
        return float(value)
    if row.get("cost_status") != "settled_gateway_debit":
        return None
    billing = row.get("billing")
    debit = billing.get("independent_gateway_debit") if isinstance(billing, dict) else None
    if not isinstance(debit, dict):
        return None
    actual, evidence = debit.get("actual_cost_cny"), debit.get("debit_evidence")
    provider = row.get("provider", "")
    from scripts import ai_providers
    root = ai_providers.PRODUCTION_PROVIDERS.get(provider, {}).get("root")
    source = ("https://cheapai.info/api/log/token" if root == "https://cheapai.info"
              else "https://codekey.ai/v1/usage" if root == "https://codekey.ai" else None)
    if (source is None or type(actual) not in {int, float} or not math.isfinite(actual) or actual < 0
            or not math.isclose(actual, value, rel_tol=0, abs_tol=1e-9)
            or not isinstance(evidence, dict) or evidence.get("source") != source
            or evidence.get("exactly_one_new_gateway_request") is not True):
        return None
    return float(value)


def cost_summary(project, spec, answer, qualified, judgments=()):
    expected = set(spec.get("cost_run_ids", []))
    candidate_runs = {run for row in answer["answer_key"] for run in row["candidate"].get("run_ids", [])}
    ledger_path = project / "state/model-usage.jsonl"
    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()] if ledger_path.is_file() else []
    selected = [row for row in rows if row.get("run_id") in expected]
    seen = {r["run_id"] for r in selected}
    complete = bool(expected) and expected == seen and candidate_runs <= expected
    total = 0.0
    identity_fields = ("run_id", "request_id", "provider", "model", "stage", "role")
    settled_ids = {tuple(row.get(k) for k in identity_fields) for row in selected
                   if settled_cost(row) is not None
                   and all(isinstance(row.get(k), str) and row[k] for k in identity_fields)}
    diagnostics = 0
    for row in selected:
        # The runtime appends a zero-cost validation diagnostic AFTER settling
        # a rejected answer. It is not another call; keep its original paid cost.
        if (row.get("validation_status") == "source_contract_failed_no_retry"
                and type(row.get("cost_cny")) in {int, float} and row["cost_cny"] == 0
                and row.get("cost_status") is None and row.get("usage_estimated") is not True
                and row.get("not_scientific_evidence") is True
                and all(isinstance(row.get(k), str) and row[k] for k in identity_fields)
                and tuple(row[k] for k in identity_fields) in settled_ids):
            diagnostics += 1
            continue
        value = settled_cost(row)
        if value is None:
            complete = False
        else:
            total += value
    from scripts.research_artifacts import bound_source
    from scripts.output_provenance import current_origin
    extra, receipts = 0.0, []
    for item in spec.get("additional_cost_receipts", []):
        bound = bound_source(project, item)
        target = path_in(project, bound["path"])
        if current_origin(project, target).get("status") != "tracked":
            raise ValueError("additional cost receipt must have current provenance")
        payload = read(target)
        amount = payload.get("amount_cny")
        if (payload.get("currency") != "CNY" or type(amount) not in {int, float}
                or not math.isfinite(amount) or amount < 0 or not payload.get("receipt_id")):
            raise ValueError("additional cost needs a finite CNY amount and actual receipt ID")
        if payload["receipt_id"] in {r["receipt_id"] for r in receipts}:
            raise ValueError("duplicate cost receipt")
        extra += amount
        receipts.append({**bound, "receipt_id": payload["receipt_id"], "amount_cny": amount})
    scope_confirmed = any(j.get("cost_scope_confirmation") == {
        "analysis_sha256": review_packets.digest(spec), "all_calls_retries_tools_compute_and_validation_included": True,
        "ledger_sha256": sha(ledger_path) if ledger_path.is_file() else None,
        "no_double_counting": True} for j in judgments)
    total_complete = complete and scope_confirmed
    return {"scope_run_ids": sorted(expected), "recorded_calls": len(selected) - diagnostics,
            "linked_validation_diagnostics": diagnostics,
            "ledger_sha256": sha(ledger_path) if ledger_path.is_file() else None,
            "known_model_cost_cny": round(total, 8), "model_cost_coverage_complete": complete,
            "model_cost_per_qualified_candidate_cny": round(total / qualified, 8) if complete and qualified else None,
            "additional_receipts": receipts, "scope_confirmed_by_owner_record": scope_confirmed,
            "total_recorded_cash_cost_cny": round(total + extra, 8) if total_complete else None,
            "total_cash_cost_per_qualified_candidate_cny": round((total + extra) / qualified, 8) if total_complete and qualified else None,
            "total_cost_status": "owner_reconciled_cash_scope" if total_complete else "cost_scope_needs_reconciliation",
            "human_effort_priced": False,
            "failures_and_retries_in_selected_runs_included": True}


def summarize(project: Path, packet_id: str) -> dict:
    document, _ = review_packets.plan(project)
    packet = next((p for p in document["packets"] if p["id"] == packet_id), None)
    if packet is None or packet["kind"] != "calibration":
        raise ValueError("a calibration packet is required")
    spec = protocol(packet)
    checked = review_packets.audit(project)
    row = next(p for p in checked["packets"] if p["id"] == packet_id)
    if row.get("status") != "pass":
        raise ValueError("packet or confirmation is stale: " + row.get("error", "unknown"))
    snapshot = review_packets.review_snapshot(project, packet_id)
    raters = {}
    for confirmation in row["confirmations"]:
        current = [a for a in confirmation["attempts"] if a["current"]]
        if current:
            last = current[-1]
            identifier = last["judgments"]["rater_id"].strip().casefold()
            if identifier in raters:
                raise ValueError("one rater cannot be counted through multiple owner records")
            raters[identifier] = last["judgments"]
    base = {"schema_version": "1.0", "packet_id": packet_id, "snapshot_sha256": snapshot["snapshot_sha256"],
            "rater_count": len(raters), "calibration_status": "NOT_CALIBRATED", "gate_approved": False,
            "scientific_completion_verified": False, "model_routing_changed": False,
            "blindness_and_qualifications_verified": False}
    if len(raters) < spec["minimum_raters"]:
        return {**base, "status": "awaiting_ratings", "candidate_results": [], "identities_revealed": False}
    answer = read(path_in(project, f"reports/review-packets/{packet_id}/answer-key.json"))
    keyed = {(r["case_label"], r["candidate_label"]): r for r in answer["answer_key"]}
    judgments = [{(r["case_label"], r["candidate_label"]): r for r in v["observations"]} for v in raters.values()]
    candidates, qualified, failed, agreements, comparisons = [], 0, 0, 0, 0
    for candidate in snapshot["roster"]:
        key = (candidate["case_label"], candidate["candidate_label"])
        ratings = [r[key] for r in judgments]
        if candidate["status"] == "failed":
            failed += 1
            candidates.append({**candidate, "qualified": False, "disposition": "unscorable_failed"})
            continue
        critical = sorted({name for r in ratings for name, value in r["critical_errors"].items() if value})
        scores = {name: {"mean": statistics.fmean(r["ratings"][name] for r in ratings),
                         "min": min(r["ratings"][name] for r in ratings), "max": max(r["ratings"][name] for r in ratings)}
                  for name in spec["qualification_thresholds"]}
        passes = not critical and all(scores[name]["min"] >= threshold for name, threshold in spec["qualification_thresholds"].items())
        qualified += int(passes)
        for left, right in itertools.combinations(ratings, 2):
            comparisons += 1
            agreements += int(left["ratings"] == right["ratings"] and left["critical_errors"] == right["critical_errors"])
        candidates.append({"case_label": key[0], "candidate_label": key[1],
            "partition": spec["case_partitions"][keyed[key]["case_id"]], "scores": scores,
            "critical_errors": critical, "qualified": passes})
    return {**base, "status": "descriptive_summary", "identities_revealed": False,
            "candidate_results": candidates, "attempts": len(candidates), "failed_attempts": failed,
            "qualified_candidates": qualified, "qualification_rate": qualified / len(candidates),
            "exact_pairwise_rating_agreement": agreements / comparisons if comparisons else None,
            "agreement_is_not_chance_corrected": True, "costs": cost_summary(project, spec, answer, qualified, raters.values()),
            "inference": "Descriptive candidate-level summaries only; cases and repeated candidates are not independent sample-size units."}


def refresh(project: Path, packet_id: str) -> dict:
    review_packets.identifier(packet_id)
    value = summarize(project, packet_id)
    output = path_in(project, f"reports/review-packets/{packet_id}/analysis.json", exists=False)
    write(output, value)
    record(project, [output], "scripts/calibration_analysis.py")
    return value
