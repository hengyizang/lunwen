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


def _prior_identity(work):
    """One source work cannot become several neighbours by changing local IDs."""
    from urllib.parse import urlsplit, urlunsplit
    from scripts.literature_evidence import _doi
    from scripts.literature_intelligence import _arxiv
    url = _text(work.get("primary_source_url"), "closest work source URL")
    parsed = urlsplit(url)
    identity_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    doi = _doi(identity_url)
    arxiv, _ = _arxiv({"doi": doi, "primary_source_url": identity_url})
    return ("arxiv:" + arxiv if arxiv else "doi:" + doi if doi else
            urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, "")))


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
    from scripts.research_methods import pinned_text_sha256
    for relative in (SOURCE + "_common.py", SOURCE + "evaluate_matrix.py"):
        _need(relative in pinned and pinned_text_sha256(path_in(ROOT, relative)) == pinned[relative]["sha256"], "pinned evaluation helper changed")
    completed = subprocess.run([sys.executable, str(ROOT / SOURCE / "evaluate_matrix.py"), str(scores), "--config", str(config),
                                "--weight-delta", str(delta)], capture_output=True, text=True, timeout=30,
                               env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    _need(completed.returncode == 0, "matrix replay failed: " + completed.stderr[-1000:])
    expected_result = json.loads(completed.stdout)
    _need(isinstance(expected_result, dict), "matrix replay must produce an object")
    _need(expected_result == json.loads(result.read_text(encoding="utf-8")) and expected_result.get("decision") is None,
          "matrix result is stale, changed or selects a winner")


def _validate(project, register, *, require_decision=True):
    _need(isinstance(register, dict), "hypothesis register must be an object")
    value = register.get("innovation_screening")
    _need(isinstance(value, dict) and value.get("schema_version") == "1.0", "innovation_screening schema_version=1.0 is required")
    mode=value.get("mode","decision")
    _choice(mode,{"exploratory","decision"},"screening mode")
    _need(not require_decision or mode=="decision","exploratory screening is still in progress; complete the decision-specific evidence before G1 approval")
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
    for row in _rows(generation["rounds"], "generation rounds", 2 if mode=="decision" else 1, 20):
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
    _need(stages[0] == "independent" and (mode=="exploratory" or "post_evidence" in stages[1:]), "retain an initial independent declaration and evidence-aware reopening")
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
    policy=value.get("comparison_policy")
    if policy is not None:
        _need(isinstance(policy,dict) and set(policy)=={"mode","focal_candidate_ids","rationale"},"focused comparison policy needs its actual candidates and rationale")
        _choice(policy["mode"],{"focused"},"comparison policy")
        focal=set(_strings(policy["focal_candidate_ids"],"focal candidates",1))
        _need(focal<=ids,"comparison policy references an unknown focal candidate")
        _text(policy["rationale"],"decision-specific comparison rationale")
        required={tuple(sorted((left,right))) for left in focal for right in ids if left!=right}
        _need(required<=pairs,"every focal candidate needs a discriminating comparison against each alternative")
    elif mode=="decision":
        _need(pairs == set(itertools.combinations(sorted(ids), 2)), "every candidate pair requires a difference and common-failure review")
    evaluation = value["evaluation"]
    _choice(evaluation["mode"], {"narrative", "weighted_matrix"}, "evaluation mode")
    _text(evaluation["method_limits"], "evaluation limits")
    for key in ("dissent", "reconciliation"):
        _strings(evaluation[key], key)
    criteria = {}
    for criterion in _rows(evaluation["criteria"], "evaluation criteria", 1 if evaluation["mode"]=="weighted_matrix" else 0, 25):
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
    for rating in _rows(evaluation["ratings"], "ratings", 1 if criteria else 0, 1000):
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


def validate(project: Path, register: dict, *, require_decision: bool = True) -> list[str]:
    """Validate declared records only; no paid calls, state changes or approval."""
    try:
        _validate(project, register,require_decision=require_decision)
    except (ValueError, TypeError, KeyError, OSError, csv.Error, subprocess.SubprocessError) as exc:
        return ["innovation_screening: " + str(exc)]
    return []


def novelty_claims(matrix: dict, gate: str, paper_id: str | None = None) -> list[dict]:
    """Scope the existing novelty record; no scores or model calls."""
    claims = _rows(matrix.get("claims"), "novelty claims", 1)
    identifiers = [_text(c.get("claim_id"), "novelty claim ID") for c in claims]
    _need(len(identifiers) == len(set(identifiers)), "novelty claim IDs must be unique")
    if gate == "G5":
        claims = [c for c in claims if paper_id in c.get("paper_ids", [])]
        _need(bool(claims), "the current paper needs its own novelty claims")
    return claims


def validate_novelty_gate(project: Path, matrix: dict, originality: dict,
                         gate: str, paper_id: str | None = None) -> list[str]:
    """Hard source requirements, followed by the actual independent review.

    Quotations and retrieval establish inspected inputs, not scientific novelty.
    Unresolved overlap cannot be offset by a score or majority vote.
    """
    try:
        from scripts.research_artifacts import read
        from scripts import literature_evidence as literature, output_provenance
        from scripts.research_extensions import _closest_prior_anchor
        from scripts.source_scope import _registered_basis
        _need(matrix.get("schema_version") == "1.1",
              "novelty matrix migration required: use 1.1 with per-work comparisons")
        prior_rows = _rows(originality.get("closest_prior_work"), "closest work", 5)
        prior = {w["id"]: w for w in prior_rows}
        _need(len(prior) == len(prior_rows) and len({_prior_identity(w) for w in prior_rows}) == len(prior_rows),
              "closest works must have distinct source identities, not aliases of the same DOI, arXiv paper or URL")
        library = _rows(read(project / "program/literature-workbench.json").get("papers"), "literature library", 1, 10000)
        searches = literature.read_jsonl(project / "evidence/search-log.jsonl")
        ledger = {r["receipt_id"]: r for r in literature.read_jsonl(project / "evidence/literature-api-ledger.jsonl")}
        from scripts.research_quality import validate_novelty_claim_matrix
        issues = validate_novelty_claim_matrix(matrix, originality, searches, project=project)
        _need(not issues, "; ".join(issues))
        validate_retrieval_dispositions(project, matrix, searches, ledger)
        for claim in novelty_claims(matrix, gate, paper_id):
            label = "novelty " + _text(claim.get("claim_id"), "claim ID")
            _text(claim.get("claim"), label + " statement")
            expected = set(_strings(claim.get("closest_work_ids"), label + " closest works", 3))
            _need(len(expected) >= 3, label + " needs three distinct closest works")
            comparisons = _rows(claim.get("prior_art_comparisons"), label + " prior_art_comparisons", 3)
            seen = set()
            for comparison in comparisons:
                work_id = _text(comparison.get("work_id"), label + " work ID")
                _need(work_id in expected and work_id in prior and work_id not in seen,
                      label + " needs one comparison against each named closest work")
                seen.add(work_id)
                work = prior[work_id]
                for key in ("already_known", "precise_difference", "non_obvious_reason", "discriminating_prediction"):
                    _text(comparison.get(key), label + "." + key)
                _need(comparison.get("disposition") == "distinct",
                      label + ": overlapping or unresolved prior art blocks the novelty gate")
                _need(comparison.get("unresolved_objections") == [], label + " has unresolved novelty objections")
                matches = [p for p in library if p.get("id") == comparison.get("library_id")]
                _need(len(matches) == 1, label + " requires one registered original source")
                paper = matches[0]
                registered, basis = _registered_basis(project, paper["id"])
                _need(registered == paper.get("source"), label + " library source differs from its protected acquisition")
                registration = read(path_in(project, basis["registration_path"]))
                candidate = registration.get("candidate", {})
                _need(isinstance(candidate, dict), label + " protected source identity is malformed")
                title = _text(work.get("title"), "closest work title")
                _need(paper.get("source_scope") == "full_text" and paper.get("url") == work.get("primary_source_url")
                      and _text(paper.get("title"), "library title").casefold() == title.casefold(),
                      label + " original source identity/full-text scope differs from the closest work")
                _need(candidate.get("canonical_id") == paper.get("candidate_id")
                      and isinstance(candidate.get("title"), str) and candidate["title"].strip().casefold() == title.casefold()
                      and candidate.get("primary_source_url") == work.get("primary_source_url"),
                      label + " source identity differs from its protected registration metadata")
                source = paper.get("source", {})
                if not str(source.get("path", "")).startswith("data/raw/literature/"):
                    origin = output_provenance.current_origin(project, path_in(project, source.get("path", "")))
                    _need(origin.get("status") == "tracked" and origin.get("provider") in
                          {"deterministic-control-plane", "human-attestation"},
                          label + " original source cannot be untracked or model-authored prose")
                anchors = _rows(comparison.get("source_anchors"), label + " source anchors", 1, 20)
                for anchor in anchors:
                    _closest_prior_anchor(project, anchor, paper)
                receipt_id = comparison.get("retrieval_receipt_id")
                receipt = ledger.get(receipt_id, {})
                bound = [r for r in searches if r.get("evidence_receipt_id") == receipt_id]
                _need(receipt.get("status") == "success" and bool(bound), label + " needs a successful retrieval receipt")
                issues = literature.validate_search_evidence(project, bound)
                _need(not issues, label + " retrieval evidence: " + "; ".join(issues))
                normalized = read(path_in(project, receipt["normalized_results_path"]))
                candidates = [w for w in normalized.get("works", []) if w.get("id") == comparison.get("retrieved_work_id")]
                _need(len(candidates) == 1 and isinstance(candidates[0].get("title"), str) and
                      candidates[0]["title"].strip().casefold() == title.casefold(),
                      label + " closest work is absent from its executed retrieval")
                doi = literature._doi(work.get("primary_source_url"))
                _need((doi and literature._doi(candidates[0].get("doi")) == doi) or
                      (not doi and candidates[0].get("url") == work.get("primary_source_url")),
                      label + " retrieved DOI/URL differs from the claimed source identity")
            _need(seen == expected, label + " omits a closest-work comparison")
        if gate in {"G2", "G5"}:
            contracts = sorted((project / "papers").glob("P[0-9][0-9]/paper-contract.json"))
            for target in contracts:
                pid = target.parent.name
                if gate == "G5" and pid != paper_id:
                    continue
                declared = set(_strings(read(target).get("independence", {}).get("unique_claim_ids"), "paper claims", 1))
                linked = {c["claim_id"] for c in matrix["claims"] if pid in c.get("paper_ids", [])}
                _need(declared == linked, pid + " contracted claims must exactly match its novelty comparisons")
        return []
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        return ["innovation hard gate: " + str(exc)]


def validate_retrieval_dispositions(project, matrix, searches, ledger):
    """Recompute returned/new identities; relevance remains an audited judgement."""
    from scripts.research_artifacts import read
    saturation = matrix["search_saturation"]
    records = {r["search_id"]: r for r in searches}
    by_search, universe = {}, set()
    for key in saturation["supporting_search_ids"]:
        receipt = ledger[records[key]["evidence_receipt_id"]]
        works = read(path_in(project, receipt["normalized_results_path"]))["works"]
        by_search[key] = {w["id"] for w in works}
        universe.update((receipt["receipt_id"], w["id"]) for w in works)
    dispositions = {}
    for row in _rows(saturation.get("retrieval_dispositions"), "retrieval_dispositions", 0, 10000):
        key = (row.get("receipt_id"), row.get("work_id"))
        _need(key in universe and key not in dispositions, "retrieval disposition is duplicated or absent from actual results")
        _choice(row.get("relevance"), {"closest", "relevant", "peripheral"}, "retrieval relevance")
        _text(row.get("rationale"), "retrieval relevance rationale")
        dispositions[key] = row["relevance"]
    _need(set(dispositions) == universe, "every retrieved work requires a relevance disposition; unknown relevance cannot count as zero")
    seen_searches, seen_works, round_ids, execution_ids = set(), set(), set(), set()
    for row in _rows(saturation.get("search_rounds"), "actual search rounds", 1):
        identifier = _text(row.get("round_id"), "search round ID")
        _need(identifier not in round_ids, "search round IDs cannot repeat")
        round_ids.add(identifier)
        keys = _strings(row.get("search_ids"), "round search IDs", 1)
        _need(len(keys) == len(set(keys)) and not seen_searches.intersection(keys)
              and set(keys) <= set(by_search), "search rounds must partition actual supporting searches")
        receipts = {records[k]["evidence_receipt_id"] for k in keys}
        _need(len(receipts) == len(keys) and not receipts.intersection(execution_ids), "renaming a search cannot create another executed round")
        execution_ids.update(receipts)
        returned = set().union(*(by_search[k] for k in keys))
        new = returned - seen_works
        closest = {work for receipt, work in dispositions if receipt in receipts and dispositions[(receipt, work)] == "closest"}
        for name, count in (("new_work_count", len(new)), ("new_closest_work_count", len(new & closest))):
            _need(type(row.get(name)) is int and row[name] == count, name + " differs from the actual returned identities and relevance dispositions")
        seen_searches.update(keys); seen_works.update(returned)
    _need(seen_searches == set(by_search), "search rounds must include every supporting retrieval")


def validate_novelty_review(audit: dict, matrix: dict, gate: str,
                            paper_id: str | None = None, *, final: bool = True) -> list[str]:
    """Claim-specific findings belong to the existing actual critic invocation."""
    try:
        claims = novelty_claims(matrix, gate, paper_id)
        expected = {c["claim_id"]: set(c["closest_work_ids"]) for c in claims}
        rows = _rows(audit.get("novelty_assessment"), "independent novelty_assessment", 1)
        seen = set()
        for row in rows:
            key = row.get("claim_id")
            _need(key in expected and key not in seen, "independent novelty review contains an unknown or duplicate claim")
            seen.add(key)
            inspected = _strings(row.get("inspected_work_ids"), "inspected closest works", 3)
            _need(len(inspected) == len(set(inspected)) and set(inspected) == expected[key],
                  "independent novelty review must inspect every linked closest work")
            _choice(row.get("decision"), {"distinct", "overlap", "unresolved"}, "novelty decision")
            _text(row.get("rationale"), "independent novelty rationale")
            _text(row.get("remaining_uncertainty"), "remaining novelty uncertainty")
            if final:
                _need(row["decision"] == "distinct", "overlap or unresolved novelty blocks advancement")
        _need(seen == set(expected), "independent novelty review omits a current claim")
        return []
    except (ValueError, KeyError, TypeError) as exc:
        return ["innovation hard gate: " + str(exc)]


def adjudication(project: Path, spec: dict, *, observed=None) -> dict:
    """Prepare current closest-work/merge questions; retain actual panel dissent."""
    from scripts.research_artifacts import read, sha
    _need(isinstance(spec, dict) and set(spec) <= {"schema_version", "id", "paper_id", "pairs"}
          and spec.get("schema_version") == "1.0", "unsupported novelty adjudication")
    identifier = _text(spec.get("id"), "adjudication ID")
    paper_id = _text(spec.get("paper_id"), "current paper")
    matrix_path = path_in(project, "program/novelty-claim-matrix.json")
    matrix = read(matrix_path)
    state_path = path_in(project, "state/run.json", exists=False)
    state = read(state_path) if state_path.is_file() else {}
    gate = state.get("gate", "G1")
    originality = {}
    try:
        originality = read(path_in(project, "program/originality-audit.json"))
        source_errors = validate_novelty_gate(project, matrix, originality, gate, paper_id)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        source_errors = [str(exc)]
    claims = {c["claim_id"]: c for c in novelty_claims(matrix, "G1")}
    pairs = []
    for pair in _rows(spec.get("pairs"), "actual merge questions", 1, 100):
        ids = _strings(pair.get("claim_ids"), "claims to contrast", 2)
        _need(len(ids) == len(set(ids)) == 2 and set(ids) <= set(claims), "merge question needs two distinct current claims")
        _need(any(paper_id in claims[k].get("paper_ids", []) for k in ids), "merge question must concern the current paper")
        pairs.append({"claim_ids": ids, "claims": [claims[k] for k in ids],
            "question": _text(pair.get("question"), "scientific merge question"), "judgments": []})
    if observed is None:
        from scripts.literature_source_tasks import judgment_responses
        observed = judgment_responses(project, paper_id)
    claim_judgments = []
    for item in observed:
        for row in item["response"].get("novelty_assessment", []):
            if row.get("claim_id") in claims:
                claim_judgments.append({**row, "review": item["receipt"]["response"], "identity": item["receipt"]["identity"]})
        for row in item["response"].get("novelty_adjudication", []):
            ids = row.get("claim_ids")
            matches = [p for p in pairs if isinstance(ids, list) and set(ids) == set(p["claim_ids"])]
            _need(len(matches) == 1 and row.get("decision") in {"distinct", "should_merge", "insufficient"}, "novelty judgment outside its current pair")
            for key in ("rationale", "shared_mechanism", "discriminating_prediction", "remaining_uncertainty"):
                _text(row.get(key), "independent novelty " + key)
            matches[0]["judgments"].append({**row, "review": item["receipt"]["response"], "identity": item["receipt"]["identity"]})
    work_ids = {work for pair in pairs for claim in pair["claims"] for work in claim.get("closest_work_ids", [])}
    nearest = [work for work in originality.get("closest_prior_work", []) if work.get("id") in work_ids]
    adjacent = originality.get("search_scope", {}).get("adjacent_fields", [])
    adjacent_ids = {field.strip().casefold() for field in adjacent if isinstance(field, str) and field.strip()}
    available = {}
    for work in nearest:
        try:
            available[work["id"]] = _prior_identity(work)
        except ValueError as exc:
            source_errors.append(str(exc))
    for pair in pairs:
        linked = {work for claim in pair["claims"] for work in claim.get("closest_work_ids", [])}
        pair["coverage_gaps"] = []
        if len({available[key] for key in linked & available.keys()}) < 5:
            pair["coverage_gaps"].append("The compared claims need at least five distinct source-bound nearest works.")
        if len(adjacent_ids) < 3:
            pair["coverage_gaps"].append("The comparison needs at least three distinct adjacent fields.")
        decisions = {r["decision"] for r in pair["judgments"]}
        pair["decision"] = next(iter(decisions)) if len(decisions) == 1 and not source_errors and not pair["coverage_gaps"] else "insufficient"
        pair["merge_concern_present"] = "should_merge" in decisions
        pair["disagreement"] = len(decisions) > 1
    source_errors.extend("/".join(pair["claim_ids"]) + ": " + gap for pair in pairs for gap in pair["coverage_gaps"])
    return {"schema_version": "1.0", "operation": "novelty_adjudication", "id": identifier,
        "paper_id": paper_id, "matrix": {"path": matrix_path.relative_to(project).as_posix(), "sha256": sha(matrix_path)},
        "pairs": pairs, "claim_novelty_judgments": claim_judgments, "source_validation_errors": source_errors,
        "nearest_works": nearest, "adjacent_fields": adjacent,
        "model_call_made": False, "novelty_verified": False, "scientific_completion_verified": False,
        "role_contract": "Return novelty_adjudication:[{claim_ids:[left,right],decision:distinct|should_merge|insufficient,rationale,shared_mechanism,discriminating_prediction,remaining_uncertainty}]. Compare OUR mechanisms with 5–8 original nearest works and at least three adjacent fields; if that source coverage is missing, retain insufficient and name the gap. Do not discard contrary works to fit a count. Test whether removing the proposed novelty leaves the same method or predictions. should_merge is a valid finding. Do not vote away dissent or infer global novelty from missing hits."}
