"""Scientific-value and discriminating-test contracts; no model calls or approvals."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = "config/scientific-reasoning.json"
STAGES = {"topic-intelligence", "paper-architecture", "experiment-design",
          "experiment-execution", "writing-and-review"}


def concrete(value, label):
    if not isinstance(value, str) or not value.strip() or normalize(value) in {"unknown", "tbd", "todo", "n/a"}:
        raise ValueError(label + " requires concrete text")
    return value


def normalize(value):
    return " ".join(value.split()).casefold()


def unique_strings(value, label):
    if not isinstance(value, list) or not value:
        raise ValueError(label + " requires a nonempty array")
    result = [concrete(item, label) for item in value]
    if len(set(result)) != len(result):
        raise ValueError(label + " contains duplicate IDs")
    return result


def load_policy(root=ROOT):
    try:
        from scripts.research_methods import safe_path
    except ImportError:
        from research_methods import safe_path
    value = json.loads(safe_path(root, POLICY).read_text(encoding="utf-8"))
    if (not isinstance(value, dict) or value.get("schema_version") != "1.0"
            or not isinstance(value.get("stages"), dict) or set(value["stages"]) != STAGES
            or not isinstance(value.get("roles"), dict) or set(value["roles"]) != {"planner", "writer", "critic"}):
        raise ValueError("invalid scientific reasoning policy identity or scopes")
    concrete(value.get("common"), "common")
    for group in ("stages", "roles"):
        for text in value[group].values():
            concrete(text, group)
    for stage in STAGES:
        for role in value["roles"]:
            if len((value["common"] + value["stages"][stage] + value["roles"][role]).encode()) > 5000:
                raise ValueError("stage-scoped scientific reasoning prompt exceeds 5000 bytes")
    return value


def stage_prompt(stage, role, root=ROOT):
    if stage not in STAGES:
        return ""
    try:
        from scripts.research_methods import sha256, safe_path
    except ImportError:
        from research_methods import sha256, safe_path
    value = load_policy(root)
    if role not in value["roles"]:
        raise ValueError("unsupported scientific reasoning role")
    return ("Scientific reasoning contract (SHA-256 " + sha256(safe_path(root, POLICY)) + "):\n"
            + value["common"] + "\n" + value["stages"][stage] + "\n" + value["roles"][role])


def validate_hypothesis_value(project, idea):
    """Replay provenance and completeness; never certify the importance or inference."""
    try:
        from scripts.research_candidates import anchor_errors
    except ImportError:
        from research_candidates import anchor_errors
    errors = []
    try:
        value = idea.get("scientific_value")
        if not isinstance(value, dict):
            raise ValueError("scientific_value is required")
        for key in ("problem", "affected_community", "why_unresolved", "knowledge_gain",
                    "practical_or_theoretical_relevance", "resource_fit", "remaining_uncertainty"):
            concrete(value.get(key), "scientific_value." + key)
        anchors = value.get("source_anchors")
        if not isinstance(anchors, list) or not anchors:
            raise ValueError("scientific_value needs located importance evidence")
        for anchor in anchors:
            relative = anchor.get("path", "") if isinstance(anchor, dict) else ""
            if (not isinstance(relative, str) or not relative.startswith(("evidence/", "literature/", "results/", "data/"))
                    or "/reviews/" in relative or "/source-scopes/" in relative):
                errors.append("scientific_value must use source evidence, not its own plan, report or approval")
            errors.extend(anchor_errors(project, anchor))
        test = idea.get("decision_test")
        if not isinstance(test, dict):
            raise ValueError("decision_test is required")
        for key in ("observable", "expected_if_hypothesis", "priority_reason",
                    "continue_if", "revise_if", "stop_if", "remaining_uncertainty"):
            concrete(test.get(key), "decision_test." + key)
        decisions = [normalize(test[k]) for k in ("continue_if", "revise_if", "stop_if")]
        if len(set(decisions)) != 3:
            errors.append("continue/revise/stop conditions must be distinguishable")
        alternatives = idea.get("alternative_explanations", [])
        predictions = [normalize(row["expected_if_true"]) for row in alternatives
                       if isinstance(row, dict) and isinstance(row.get("expected_if_true"), str)]
        if normalize(test["expected_if_hypothesis"]) in predictions:
            errors.append("the focal and alternative predictions are identical; the test does not discriminate")
    except (ValueError, TypeError, KeyError) as exc:
        errors.append(str(exc))
    return errors


def validate_critical_tests(protocol, project=None):
    """Bind scientific questions to existing comparisons; alter no run order or budget."""
    comparisons = {row["comparison_id"]: row for row in protocol["comparisons"]}
    hypothesis_ids = None
    if project is not None:
        register = project / "program/hypothesis-register.json"
        if register.exists() or register.is_symlink() or "hypothesis_register" in protocol:
            import hashlib
            try:
                from scripts.research_methods import safe_path
            except ImportError:
                from research_methods import safe_path
            register = safe_path(project, "program/hypothesis-register.json")
            if not register.is_file():
                raise ValueError("bound hypothesis_register is missing")
            binding = protocol.get("hypothesis_register")
            if (not isinstance(binding, dict) or binding.get("path") != "program/hypothesis-register.json"
                    or binding.get("sha256") != hashlib.sha256(register.read_bytes()).hexdigest()):
                raise ValueError("critical tests need the exact current hypothesis_register binding")
            value = json.loads(register.read_text(encoding="utf-8"))
            hypotheses = value.get("hypotheses") if isinstance(value, dict) else None
            if not isinstance(hypotheses, list) or any(not isinstance(h, dict) or not isinstance(h.get("hypothesis_id"), str) for h in hypotheses):
                raise ValueError("critical tests need actual registered hypothesis IDs")
            hypothesis_ids = {h["hypothesis_id"] for h in hypotheses}
            if len(hypothesis_ids) != len(hypotheses):
                raise ValueError("duplicate registered hypothesis IDs")
    tests = protocol.get("critical_tests")
    if not isinstance(tests, list) or not 1 <= len(tests) <= 100:
        raise ValueError("critical_tests requires 1-100 discriminating test records")
    identifiers, covered = set(), set()
    expected = {(c["hypothesis_id"], claim, cid) for cid, c in comparisons.items() for claim in c["claim_ids"]}
    for row in tests:
        if not isinstance(row, dict):
            raise ValueError("critical test must be an object")
        identifier = concrete(row.get("test_id"), "critical test_id")
        if identifier in identifiers:
            raise ValueError("duplicate critical test_id")
        identifiers.add(identifier)
        for key in ("hypothesis_id", "scientific_question", "mechanism_or_rationale",
                    "expected_if_hypothesis", "priority_reason", "practical_or_theoretical_relevance",
                    "continue_if", "revise_if", "stop_if", "remaining_uncertainty"):
            concrete(row.get(key), "critical test." + key)
        if hypothesis_ids is not None and row["hypothesis_id"] not in hypothesis_ids:
            raise ValueError("critical test hypothesis is absent from the bound register")
        if len({normalize(row[k]) for k in ("continue_if", "revise_if", "stop_if")}) != 3:
            raise ValueError("critical test continue/revise/stop conditions must differ")
        claims = unique_strings(row.get("claim_ids"), "critical claim_ids")
        ids = unique_strings(row.get("comparison_ids"), "critical comparison_ids")
        alternatives = row.get("alternative_explanations")
        if not isinstance(alternatives, list) or len(alternatives) < 2:
            raise ValueError("critical test needs at least two alternative explanations")
        explanations = set()
        for alternative in alternatives:
            if not isinstance(alternative, dict):
                raise ValueError("critical alternative must be an object")
            explanation = normalize(concrete(alternative.get("explanation"), "alternative explanation"))
            prediction = normalize(concrete(alternative.get("expected_if_true"), "alternative prediction"))
            if explanation in explanations or prediction == normalize(row["expected_if_hypothesis"]):
                raise ValueError("critical explanations/predictions must be distinguishable")
            explanations.add(explanation)
        for cid in ids:
            comp = comparisons.get(cid)
            if comp is None or comp["hypothesis_id"] != row["hypothesis_id"] or not set(claims) <= set(comp["claim_ids"]):
                raise ValueError("critical test comparison/hypothesis/claim binding differs from the actual protocol")
            covered.update((row["hypothesis_id"], claim, cid) for claim in claims)
    if covered != expected:
        raise ValueError("critical tests must cover every claim/comparison, including adverse controls and baselines")
    return tests


def critical_test_results(protocol, rows):
    """Expose every numeric decision without declaring mechanism, novelty or a stop."""
    indexed = {row["comparison_id"]: row for row in rows}
    result = []
    for test in protocol["critical_tests"]:
        observations = [indexed.get(cid, {"comparison_id": cid, "status": "missing", "decision": "incomplete"})
                        for cid in test["comparison_ids"]]
        result.append({
            "test_id": test["test_id"], "hypothesis_id": test["hypothesis_id"], "claim_ids": test["claim_ids"],
            "comparison_ids": test["comparison_ids"],
            "comparison_decisions": [{k: row.get(k) for k in ("comparison_id", "status", "decision")} for row in observations],
            "threshold_not_established_ids": [r["comparison_id"] for r in observations if r.get("decision") != "meets_preregistered_threshold"],
            "evidence_status": ("numeric_results_require_scientific_review" if all(r.get("status") == "computed" for r in observations) else "incomplete"),
            "remaining_uncertainty": test["remaining_uncertainty"],
            "alternative_explanations": test["alternative_explanations"],
            "declared_next_step_conditions": {key: test[key] for key in ("continue_if", "revise_if", "stop_if")},
            "mechanism_established": False, "scientific_significance_verified": False,
            "automatic_stop_or_execution_authorized": False,
        })
    return result
