"""Deterministic cost diagnostics. Never remove scientific reviews or call models."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


REPORT = "state/cost-audit.json"


def summarize(entries: list[dict]) -> dict:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    fresh, unknown, unbound = 0, 0, 0
    for item in entries:
        if item.get("cache_hit") is True:
            continue
        role = str(item.get("role") or "")
        if str(item.get("cost_status") or "").startswith(("unknown", "estimated")):
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
        candidates.append({"stage": key[0], "paper_id": key[1], "role": key[2],
                           "provider": key[3], "model": key[4], "cache_key": key[-1],
                           "attempt_count": len(rows), "run_ids": [r.get("run_id") for r in rows],
                           "known_recorded_cost_cny": round(sum(float(r.get("cost_cny") or 0)
                               for r in rows if not str(r.get("cost_status") or "").startswith(("unknown", "estimated"))), 8),
                           "billing_uncertain": any(str(r.get("cost_status") or "").startswith(("unknown", "estimated")) for r in rows),
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
