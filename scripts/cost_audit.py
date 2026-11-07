"""Deterministic cost diagnostics. Never remove scientific reviews or call models."""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


REPORT = "state/cost-audit.json"


def _role(item: dict) -> str:
    role = str(item.get("role", "")).casefold()
    if "planner" in role or role == "semantic-plan":
        return "planner"
    if any(word in role for word in ("critic", "review", "panel")):
        return "critic"
    if any(word in role for word in ("writer", "author", "remediat")):
        return "writer"
    return "other"


def _amount(value):
    try:
        return float(value) if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None
    except OverflowError:
        return None


def _recorded_cost(row):
    # A failed controlled request writes a zero placeholder while its real
    # reservation remains outstanding. It is not an observed free model call.
    if row.get("zero_cost_not_confirmed") or str(row.get("cost_status", "")).startswith(("unknown", "accounted_upper")):
        return None
    return _amount(row.get("cost_cny"))


def _uncertain_billing(row):
    return (_recorded_cost(row) is None
            or str(row.get("cost_status", "")).startswith(("unknown", "estimated", "accounted_upper")))


def portfolio_forecast(entries: list[dict], paper_count: int = 6) -> dict:
    """Observed-call scenarios, never a promise about papers, quality or elapsed days."""
    if type(paper_count) is not int or paper_count < 1:
        raise ValueError("paper_count must be a positive integer")
    rows = [row for row in entries if not row.get("validation_status") and row.get("cache_hit") is not True]
    samples, allocation = {}, {}
    for role in ("planner", "writer", "critic", "other"):
        selected = [row for row in rows if _role(row) == role]
        costs = [_recorded_cost(row) for row in selected]
        seconds = [_amount(row.get("duration_seconds")) for row in selected]
        samples[role] = {"count": len(selected), "cost_cny": [x for x in costs if x is not None],
                         "seconds": [x for x in seconds if x is not None]}
        allocation[role] = {"attempts": len(selected),
            "known_recorded_cost_cny": round(sum(x for x in costs if x is not None), 8),
            "cost_unknown_attempts": costs.count(None),
            "estimated_billing_attempts": sum(str(row.get("cost_status", "")).startswith(("unknown", "estimated", "accounted_upper")) for row in selected),
            "known_duration_seconds": round(sum(x for x in seconds if x is not None), 3),
            "duration_unknown_attempts": seconds.count(None)}
    scenarios = []
    for name, shared, per_paper in (("few_iterations", 1, 3), ("planning_example", 3, 6), ("many_iterations", 6, 12)):
        cycles = shared + paper_count * per_paper
        counts = {"planner": cycles + paper_count, "writer": cycles + paper_count,
                  "critic": cycles + 3 * paper_count}
        row = {"name": name, "shared_ordinary_cycles": shared, "ordinary_cycles_per_paper": per_paper,
               "submission_panel_reviews_per_paper": 3, "calls_by_role": counts,
               "model_calls": sum(counts.values()), "cost_cny": None,
               "serial_model_seconds": None, "missing_samples": []}
        for metric, sample in (("cost_cny", "cost_cny"), ("serial_model_seconds", "seconds")):
            missing = [role for role in counts if not samples[role][sample]
                       or len(samples[role][sample]) != samples[role]["count"]]
            if missing:
                row["missing_samples"].append({"metric": metric, "roles": missing})
            else:
                row[metric] = {name: round(sum(counts[role] * function(samples[role][sample]) for role in counts), 6)
                               for name, function in (("observed_low", min), ("observed_median", statistics.median), ("observed_high", max))}
        scenarios.append(row)
    return {"paper_count": paper_count, "scenarios": scenarios, "observed_role_allocation": allocation,
            "control_roles": ["planner", "critic"], "research_writing_roles": ["writer"],
            "scientific_success_or_acceptance_predicted": False,
            "assumptions": ["Illustrative iteration counts, not execution quotas or a validated six-paper forecast.",
                "Each ordinary cycle has three calls; each paper adds one final planner/writer/three-reviewer submission cycle (five calls).",
                "Extra repairs, repeat panels, source acquisition and experiments are additional.",
                "Observed role prices may differ from future model routes; these are estimates, not billing quotes.",
                "Model seconds are summed service time, not wall time, research duration or a completion deadline.",
                "Compute USD and API CNY remain separate; no currency conversion or increased authority is assumed."]}


def summarize(entries: list[dict]) -> dict:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    fresh, unknown, unbound = 0, 0, 0
    for item in entries:
        if item.get("cache_hit") is True:
            continue
        role = str(item.get("role") or "")
        if _uncertain_billing(item):
            unknown += 1
        if role.startswith("independent-critic") or role in {"independent-critique", "endpoint-health"}:
            fresh += 1
            continue  # The same input can intentionally need fresh assessments.
        fingerprint = item.get("cache_key")
        if not fingerprint:
            unbound += 1
            continue
        key = (item.get("stage"), item.get("paper_id"), role, item.get("provider"),
               item.get("model"), item.get("endpoint"), item.get("billing_quote_sha256"),
               json.dumps(item.get("billing_identity") or {}, sort_keys=True), fingerprint)
        groups[key].append(item)
    candidates = []
    for key, rows in groups.items():
        if len(rows) < 2:
            continue
        known_costs = [_recorded_cost(row) for row in rows if not _uncertain_billing(row)]
        candidates.append({"stage": key[0], "paper_id": key[1], "role": key[2],
                           "provider": key[3], "model": key[4], "cache_key": key[-1],
                           "attempt_count": len(rows), "run_ids": [r.get("run_id") for r in rows],
                           "known_recorded_cost_cny": round(sum(known_costs), 8) if known_costs else None,
                           "billing_uncertain": any(_uncertain_billing(row) for row in rows),
                           "action": "inspect purpose and receipts; never skip automatically"})
    return {"schema_version": "1.0", "ledger_entries": len(entries),
            "cache_hits": sum(item.get("cache_hit") is True for item in entries),
            "fresh_review_or_health_attempts": fresh, "uncertain_billing_entries": unknown,
            "legacy_attempts_without_fingerprint": unbound,
            "duplicate_paid_request_candidates": candidates,
            "duplicate_candidates_prove_waste": False,
            "savings_or_scientific_equivalence_proven": False,
            "no_model_calls": True, "no_routing_or_approval_changes": True}


def refresh(project: Path) -> dict:
    from scripts import model_runtime
    from scripts.research_artifacts import write
    report = summarize(model_runtime.ledger_entries(project))
    from scripts.research_artifacts import read
    state = read(project / "state/run.json") if (project / "state/run.json").is_file() else {}
    paper_count = state.get("paper_count", 6)
    report["portfolio_forecast"] = portfolio_forecast(model_runtime.ledger_entries(project), paper_count)
    report["budget"] = model_runtime.budget_status(project)
    # CLI/subscription usage is a separate accounting domain; don't report it
    # as free merely because an API usage ledger has no corresponding rows.
    journals = list((project / "state/runs").glob("*/journal.json"))
    report["cli_journal_count"] = len(journals)
    report["cli_subscription_spend_not_measured_by_api_ledger"] = bool(journals)
    report["historical_transcript_bytes_excluded_from_prompts"] = sum(
        path.stat().st_size for path in (project / "state/runs").rglob("*")
        if path.is_file() and not path.is_symlink())
    write(project / REPORT, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    from scripts.api_orchestrator import project_root
    print(json.dumps(refresh(project_root(args.project)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
