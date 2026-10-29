"""Source-bound proposal screening inside the existing hypothesis register.

Completeness, exact duplicate detection and replayable records never establish
semantic independence, novelty, scientific validity or human gate approval.
"""
from __future__ import annotations

import csv
import itertools
import json
import math
import os
from pathlib import Path
import subprocess
import sys

try:
    from scripts.research_artifacts import path_in, sha
except ImportError:
    from research_artifacts import path_in, sha

ROOT = Path(__file__).resolve().parents[1]
MODULE = "scripts/innovation_screening.py"
SOURCE = "third_party/kdense/skills/scientific-brainstorming/scripts/"


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _text(value, label):
    _need(isinstance(value, str) and bool(value.strip()) and len(value) <= 8000, label + " needs bounded concrete text")
    return value.strip()


def _rows(value, label, minimum=0, maximum=100):
    _need(isinstance(value, list) and minimum <= len(value) <= maximum and all(isinstance(r, dict) for r in value), label + " needs bounded object records")
    return value


def _strings(value, label, minimum=0):
    _need(isinstance(value, list) and minimum <= len(value) <= 100, label + " needs a bounded string list")
    return [_text(v, label) for v in value]


def _choice(value, options, label):
    _need(isinstance(value, str) and value in options, label + " has an unsupported status")


def _anchors(project, values, label):
    try:
        from scripts.research_candidates import anchor_errors
    except ImportError:
        from research_candidates import anchor_errors
    for anchor in _rows(values, label):
        errors = anchor_errors(project, anchor)
        _need(not errors, label + ": " + "; ".join(errors))


def _binding(project, value):
    _need(isinstance(value, dict) and set(value) == {"path", "sha256"}, "record binding needs exactly path and sha256")
    _text(value["path"], "binding path")
    target = path_in(project, value["path"])
    _need(sha(target) == value["sha256"], "stale bound innovation input: " + value["path"])
    return target


def _number(value, label):
    _need(type(value) in {int, float} and math.isfinite(value), label + " needs a finite number")
    return value


def _matrix(project, evaluation, criteria, current, candidate_ids):
    try:
        from scripts.literaturectl import require_cloud
    except ImportError:
        from literaturectl import require_cloud
    require_cloud()
    matrix = evaluation["matrix"]
    _need(isinstance(matrix, dict), "weighted evaluation needs a bound matrix")
    rater = _text(matrix.get("rater_id"), "matrix rater_id")
    delta = _number(matrix.get("weight_delta"), "weight_delta")
    _need(0 <= delta <= .5, "weight_delta must be within 0..0.5")
    deferred = _strings(matrix.get("deferred_candidate_ids"), "deferred candidates")
    _need(len(set(deferred)) == len(deferred) and set(deferred) <= candidate_ids, "invalid deferred candidate IDs")
    config = _binding(project, matrix.get("criteria_file"))
    scores = _binding(project, matrix.get("scores_file"))
    result = _binding(project, matrix.get("result_file"))
    supplied = json.loads(config.read_text(encoding="utf-8"))
    _need(isinstance(supplied, dict), "matrix criteria configuration must be an object")
    expected = [{"name": c["criterion_id"], "description": c["definition"], "weight": c["weight"],
                 "direction": c["direction"], "minimum": c["minimum"], "maximum": c["maximum"]} for c in criteria.values()]
    _need(supplied.get("schema_version") == "1.0" and supplied.get("criteria") == expected, "matrix criteria differ from the declared criteria/weights")
    _need(all(c["weight"] is not None for c in criteria.values()), "weighted criteria need explicit positive weights")
    with scores.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    _need(len(rows) <= 100 and len({r.get("idea_id") for r in rows}) == len(rows), "duplicate or excessive matrix rows")
    _need({r.get("idea_id") for r in rows} == candidate_ids - set(deferred), "matrix rows must cover exactly the nondeferred candidates")
    for identity in candidate_ids:
        missing = any(current.get((identity, key, rater), {}).get("score") is None for key in criteria)
        _need(not missing or identity in deferred, "missing or abstained ratings require explicit deferral; never zero imputation")
    for row in rows:
        for key in criteria:
            rating = current[(row["idea_id"], key, rater)]
            _need(float(row[key]) == rating["score"], "matrix score differs from the selected current rating")
            for suffix in ("low", "high"):
                cell = row.get(key + "_" + suffix, "")
                _need(isinstance(cell, str), "matrix CSV row is truncated or has a missing bounds cell")
                if rating[suffix] is None:
                    _need(not cell.strip(), "unassessed rating bounds cannot become a point interval")
                else:
                    _need(bool(cell.strip()) and float(cell) == rating[suffix], "matrix bound differs from its recorded rating")
    # Only the reviewed deterministic CLI is executed. It uses no credentials,
    # network, models or experiment authority, and writes nothing without --output.
    manifest = json.loads((ROOT / "integrations/vendored-research-methods.json").read_text(encoding="utf-8"))
    pinned = {r["path"]: r for r in manifest["files"]}
    for relative in (SOURCE + "_common.py", SOURCE + "evaluate_matrix.py"):
        _need(relative in pinned and sha(path_in(ROOT, relative)) == pinned[relative]["sha256"], "pinned evaluation helper changed")
    completed = subprocess.run([sys.executable, str(ROOT / SOURCE / "evaluate_matrix.py"), str(scores), "--config", str(config),
                                "--weight-delta", str(delta)], capture_output=True, text=True, timeout=30,
                               env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    _need(completed.returncode == 0, "matrix replay failed: " + completed.stderr[-1000:])
    expected_result = json.loads(completed.stdout)
    _need(isinstance(expected_result, dict), "matrix replay must produce an object")
    _need(expected_result == json.loads(result.read_text(encoding="utf-8")) and expected_result.get("decision") is None,
          "matrix result is stale, changed or selects a winner")


def _validate(project, register):
    _need(isinstance(register, dict), "hypothesis register must be an object")
    value = register.get("innovation_screening")
    _need(isinstance(value, dict) and value.get("schema_version") == "1.0", "innovation_screening schema_version=1.0 is required")
    hypotheses = {h["hypothesis_id"]: h for h in register["hypotheses"]}
    ids = set(hypotheses)
    _need(3 <= len(ids) <= 30, "innovation screening needs three to thirty candidate hypotheses")
    normalized = [tuple(" ".join(_text(h[key], "candidate " + key).casefold().split()) for key in ("hypothesis", "prediction", "precise_difference")) for h in hypotheses.values()]
    _need(len(set(normalized)) == len(normalized), "candidate IDs repeat the exact same hypothesis, prediction and precise difference")
    scope = value["scope"]
    _need(scope["focal_question"] == register["argument_plan"]["research_question"], "screening focal question differs from the registered research question")
    _text(scope["doctoral_question"], "doctoral_question")
    for key in ("in_scope", "out_of_scope"):
        _strings(scope[key], key, 1)
    for constraint in _rows(scope["constraints"], "constraints", 1):
        _text(constraint["statement"], "constraint")
        _choice(constraint["status"], {"real", "assumed", "negotiable", "unknown"}, "constraint")
    generation = value["generation"]
    for key in ("method", "reason"):
        _text(generation[key], key)
    for key in ("represented_perspectives", "missing_perspectives", "prior_examples", "deviations"):
        _strings(generation[key], key, 1 if key == "represented_perspectives" else 0)
    _choice(generation["independence"], {"declared", "not_achieved", "unknown"}, "independence")
    _need(generation["independence"] == "declared" or bool(generation["deviations"]), "unknown/unachieved independent generation needs a truthful deviation")
    contributors = _rows(generation["contributors"], "contributors", 1)
    contributor_ids = set()
    for contributor in contributors:
        identity = _text(contributor["contributor_id"], "contributor_id")
        _need(identity not in contributor_ids, "duplicate contributor ID")
        contributor_ids.add(identity)
        _choice(contributor["kind"], {"human", "model"}, "contributor kind")
        _text(contributor["tool_and_purpose"], "tool_and_purpose")
    _need(any(c["kind"] == "human" for c in contributors) or bool(generation["deviations"]), "AI-only ideation must disclose its human-first process adaptation")
    stages, round_ids, retained_ideas = [], set(), {}
    for row in _rows(generation["rounds"], "generation rounds", 2, 20):
        identity = _text(row["round_id"], "round_id")
        _need(identity not in round_ids, "duplicate generation round ID")
        round_ids.add(identity)
        _choice(row["stage"], {"independent", "discussion", "post_evidence"}, "round stage")
        selected = _strings(row["candidate_ids"], "round candidates", 1)
        _need(len(set(selected)) == len(selected) and set(selected) <= ids, "round has duplicate or unknown candidate IDs")
        source = _binding(project, row["record_binding"])
        recorded = json.loads(source.read_text(encoding="utf-8"))
        _need(isinstance(recorded, dict), "retained round record must be an object")
        _need(all(recorded.get(k) == row[k] for k in ("round_id", "stage", "candidate_ids")), "generation declaration differs from its retained round record")
        originals = _rows(recorded.get("ideas"), "retained original ideas", 1, 30)
        _need(len(originals) == len(selected) and {i.get("hypothesis_id") for i in originals} == set(selected), "round must retain each original idea, not only its ID")
        for idea in originals:
            for key in ("statement", "prediction", "precise_difference"):
                _text(idea.get(key), "retained original idea " + key)
            retained_ideas[idea["hypothesis_id"]] = idea
        inputs = _rows(recorded.get("evidence_inputs"), "round evidence inputs")
        limits = _strings(recorded.get("evidence_limits"), "round evidence limits")
        for binding in inputs:
            _binding(project, binding)
        _need(row["stage"] != "post_evidence" or bool(inputs or limits), "evidence reopening needs bound inputs or explicit search limits")
        stages.append(row["stage"])
    _need(stages[0] == "independent" and "post_evidence" in stages[1:], "retain an initial independent declaration and evidence-aware reopening")
    _need(set(retained_ideas) == ids, "every current candidate needs a retained original idea")
    for identity, idea in retained_ideas.items():
        _need(all(" ".join(idea[left].casefold().split()) == " ".join(hypotheses[identity][right].casefold().split())
                  for left, right in (("statement", "hypothesis"), ("prediction", "prediction"), ("precise_difference", "precise_difference"))),
              "current candidate differs from its latest retained round; preserve a new revision record")
    for event in _rows(generation["clustering_events"], "clustering events"):
        _choice(event["action"], {"merge", "split", "group"}, "cluster action")
        for key in ("original_candidate_ids", "result_candidate_ids"):
            _need(set(_strings(event[key], key, 1)) <= ids, "cluster must preserve original and result candidate IDs")
        _text(event["relation"], "cluster relation")
        _text(event["rationale"], "cluster rationale")
    assumptions = {}
    for row in _rows(value["assumptions"], "assumptions", 1):
        identity = _text(row["assumption_id"], "assumption_id")
        _need(identity not in assumptions, "duplicate assumption ID")
        assumptions[identity] = row
        for key in ("statement", "test_or_check", "failure_consequence"):
            _text(row[key], "assumption " + key)
        _choice(row["category"], {"causal", "mechanistic", "measurement", "sampling", "operational", "statistical", "feasibility", "ethical", "value", "background"}, "assumption category")
        _choice(row["status"], {"untested", "support_located", "challenge_located", "mixed"}, "assumption status")
        selected = _strings(row["candidate_ids"], "assumption candidates", 1)
        _need(len(set(selected)) == len(selected) and set(selected) <= ids, "assumption has invalid candidate references")
        _anchors(project, row["source_anchors"], "assumption evidence")
        _need(row["status"] == "untested" or bool(row["source_anchors"]), "a located assumption status needs actual source anchors")
    candidates = {}
    for row in _rows(value["candidates"], "screened candidates", len(ids), len(ids)):
        identity = row["hypothesis_id"]
        _need(isinstance(identity, str) and identity in ids and identity not in candidates, "candidate screening must cover every hypothesis once")
        candidates[identity] = row
        _text(row["mechanism"], "candidate mechanism")
        refs = _strings(row["assumption_ids"], "candidate assumptions", 1)
        _need(len(set(refs)) == len(refs) and set(refs) <= set(assumptions), "candidate references duplicate or unknown assumptions")
        _need(set(refs) == {k for k, a in assumptions.items() if identity in a["candidate_ids"]}, "assumption references must agree in both directions")
        _choice(row["evidence_status"], {"not_checked", "search_incomplete", "support_located", "challenge_located", "mixed"}, "candidate evidence status")
        _anchors(project, row["evidence_for"], "support evidence")
        _anchors(project, row["evidence_against"], "challenge evidence")
        if row["evidence_status"] in {"support_located", "mixed"}:
            _need(bool(row["evidence_for"]), "support-located candidate needs actual evidence")
        if row["evidence_status"] in {"challenge_located", "mixed"}:
            _need(bool(row["evidence_against"]), "challenge-located candidate needs actual evidence")
        _strings(row["search_limits"], "search limits", 1)
        gaps = _rows(row["evidence_gaps"], "candidate evidence gaps", 1)
        gap_ids = set()
        for gap in gaps:
            _need(_text(gap["gap_id"], "gap ID") not in gap_ids, "duplicate evidence gap ID")
            gap_ids.add(gap["gap_id"])
            for key in ("question", "resolution_test", "next_action"):
                _text(gap[key], "gap " + key)
        exposure = row["prior_exposure"]
        _choice(exposure["status"], {"none", "seen", "unknown"}, "data exposure")
        for key in ("details", "future_confirmatory_evidence"):
            _text(exposure[key], "exposure " + key)
        _choice(exposure["analysis_phase"], {"exploratory", "prospective"}, "candidate analysis phase")
        _need(exposure["status"] == "none" or exposure["analysis_phase"] == "exploratory", "seen/unknown outcome exposure must remain exploratory")
        inputs = _rows(exposure["observed_inputs"], "observed inputs", 1 if exposure["status"] == "seen" else 0)
        _need(exposure["status"] != "none" or not inputs, "no-exposure claim contradicts observed inputs")
        for binding in inputs:
            _binding(project, binding)
        for check in _rows(row["adversarial_checks"], "adversarial self-checks", 1):
            for key in ("challenge", "response", "next_test", "residual_uncertainty"):
                _text(check[key], "adversarial " + key)
        disposition = row["disposition"]
        _choice(disposition["status"], {"retain", "revise", "defer", "reject"}, "candidate disposition")
        for key in ("rationale", "next_action", "revisit_when", "owner"):
            _text(disposition[key], "disposition " + key)
        gates = row["gate_status"]
        for key in ("feasibility", "rigor", "ethics"):
            _choice(gates[key], {"not_assessed", "review_required", "no_block_identified", "blocked", "not_applicable"}, "proposal gate " + key)
        _need(disposition["status"] != "retain" or "blocked" not in gates.values(), "a blocked hard gate cannot be offset by a rating")
    pairs = set()
    for row in _rows(value["comparisons"], "candidate comparisons", maximum=435):
        selected = _strings(row["candidate_ids"], "comparison candidates", 2)
        _need(len(selected) == 2 and len(set(selected)) == 2 and set(selected) <= ids, "comparison requires two distinct known candidates")
        pair = tuple(sorted(selected))
        _need(pair not in pairs, "duplicate candidate comparison")
        pairs.add(pair)
        for key in ("mechanism_difference", "prediction_difference", "distinguishing_test", "common_failure_risk"):
            _text(row[key], "comparison " + key)
        shared = _strings(row["shared_assumption_ids"], "shared assumptions")
        _need(len(set(shared)) == len(shared) and set(shared) == set(candidates[pair[0]]["assumption_ids"]) & set(candidates[pair[1]]["assumption_ids"]), "shared-assumption comparison must expose every declared common dependency")
    _need(pairs == set(itertools.combinations(sorted(ids), 2)), "every candidate pair requires a difference and common-failure review")
    evaluation = value["evaluation"]
    _choice(evaluation["mode"], {"narrative", "weighted_matrix"}, "evaluation mode")
    _text(evaluation["method_limits"], "evaluation limits")
    for key in ("dissent", "reconciliation"):
        _strings(evaluation[key], key)
    criteria = {}
    for criterion in _rows(evaluation["criteria"], "evaluation criteria", 1, 25):
        key = _text(criterion["criterion_id"], "criterion ID")
        _need(key not in criteria, "duplicate evaluation criterion")
        criteria[key] = criterion
        _text(criterion["definition"], "criterion definition")
        _choice(criterion["direction"], {"higher", "lower"}, "criterion direction")
        _need(_number(criterion["minimum"], "criterion minimum") < _number(criterion["maximum"], "criterion maximum"), "criterion scale requires minimum below maximum")
        _need(len(_strings(criterion["anchors"], "scale anchors", 3)) == 3, "criterion needs low, midpoint and high anchors")
        if criterion["weight"] is not None:
            _need(_number(criterion["weight"], "criterion weight") > 0, "criterion weights must be positive")
    ratings, replaced, current = {}, set(), {}
    for rating in _rows(evaluation["ratings"], "ratings", 1, 1000):
        identity = _text(rating["rating_id"], "rating ID")
        _need(identity not in ratings, "duplicate rating ID")
        h, c, rater = rating["hypothesis_id"], rating["criterion_id"], _text(rating["rater_id"], "rater ID")
        _need(isinstance(h, str) and h in ids and isinstance(c, str) and c in criteria, "rating references an unknown candidate or criterion")
        key = (h, c, rater)
        previous = rating["supersedes"]
        if previous is not None:
            _need(isinstance(previous, str) and previous in ratings and previous not in replaced and current.get(key) is ratings[previous], "rating revision must retain and supersede its current predecessor")
            replaced.add(previous)
        else:
            _need(key not in current, "duplicate current rating without an explicit revision")
        current[key] = rating
        ratings[identity] = rating
        _text(rating["rationale"], "rating rationale or abstention")
        _anchors(project, rating["source_anchors"], "rating source anchors")
        score, low, high = rating["score"], rating["low"], rating["high"]
        _need((low is None) == (high is None), "rating uncertainty bounds must both be supplied or both remain unknown")
        if score is None:
            _need(low is None and high is None, "abstention cannot have numeric bounds")
        else:
            _need(criteria[c]["minimum"] <= _number(score, "rating score") <= criteria[c]["maximum"], "rating score is outside its anchored scale")
            if low is not None:
                _need(criteria[c]["minimum"] <= _number(low, "rating low") <= score <= _number(high, "rating high") <= criteria[c]["maximum"], "rating bounds must contain the score within the scale")
    _need({(h, c) for h, c, _ in current} == set(itertools.product(ids, criteria)), "each candidate/criterion requires a rating or explicit abstention")
    if evaluation["mode"] == "weighted_matrix":
        _matrix(project, evaluation, criteria, current, ids)
    else:
        _need(evaluation["matrix"] is None, "narrative evaluation cannot silently attach a weighted winner")


def validate(project: Path, register: dict) -> list[str]:
    """Validate declared records only; no paid calls, state changes or approval."""
    try:
        _validate(project, register)
    except (ValueError, TypeError, KeyError, OSError, csv.Error, subprocess.SubprocessError) as exc:
        return ["innovation_screening: " + str(exc)]
    return []
