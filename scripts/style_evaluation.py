"""Offline counterexample evaluation for scientific editing, not AI detection."""
from __future__ import annotations

import json
from pathlib import Path
from scripts.scientific_editing import context_changes


def evaluate(cases: list[dict]) -> dict:
    results = []
    for case in cases:
        if not case.get("id") or not isinstance(case.get("must_flag"), bool):
            raise ValueError("evaluation cases need ID and expected protection outcome")
        changes = context_changes(case["before"], case["after"])
        flagged = bool(changes["added"] or changes["removed"])
        results.append({"id": case["id"], "expected": case["must_flag"], "flagged": flagged,
                        "correct": flagged == case["must_flag"], "category": case["category"]})
    return {"schema_version": "1.0", "results": results,
            "passed": sum(r["correct"] for r in results), "total": len(results),
            "status": "pass" if results and all(r["correct"] for r in results) else "fail",
            "calibration_status": "NOT_CALIBRATED", "authorship_detection": False,
            "scientific_equivalence_proven": False, "human_review_required": True}


def repository_cases() -> list[dict]:
    path = Path(__file__).resolve().parents[1] / "config/scientific-editing-eval.json"
    return json.loads(path.read_text(encoding="utf-8"))["cases"]
