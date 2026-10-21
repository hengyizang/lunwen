"""Source-bound reading feedback and reviewed discovery improvements, without calls.

Events and proposals are immutable. A proposal may adjust discovery weights or
add explicitly suggested keywords only after an owner-authorized review. It can
never alter the doctoral question, exclusions, searches, scientific gates or
spending controls. Operational follow-ups preserve blocked/contrary sources.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re

from scripts import literature_evidence as evidence
from scripts import literature_intelligence as intelligence
from scripts.output_provenance import current_origin
from scripts.research_artifacts import bound_source, path_in, read, record, sha, write

ROOT = "reports/literature-feedback"
OUTCOMES = {
    "relevance": {"relevant", "partly_relevant", "irrelevant", "unknown"},
    "duplicates": {"distinct", "duplicate", "version", "unknown"},
    "source_accessibility": {"accessible", "blocked", "missing", "unknown"},
    "evidence_sufficiency": {"sufficient", "partial", "insufficient", "unknown"},
    "experiment_utility": {"used", "promising", "not_useful", "not_evaluated"},
}
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z")
MODULE = "scripts/literature_feedback.py"


def digest(value) -> str:
    return hashlib.sha256(evidence.canonical_json_bytes(value)).hexdigest()


def _cloud():
    if os.environ.get("GITHUB_ACTIONS") != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1":
        raise RuntimeError("literature feedback runs only on the declared cloud executor")


def _text(value, name, maximum=4000):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
        raise ValueError(name + " needs explicit bounded text")
    return value.strip()


def _id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("invalid feedback/proposal identifier")
    return value


def _trusted(project, path):
    origin = current_origin(project, path)
    if origin.get("status") != "tracked" or origin.get("family") == "anthropic":
        raise ValueError("feedback inputs require current non-Claude provenance")


def _plan(project, plan_path, expected=None):
    if plan_path != intelligence.PLAN:
        raise ValueError("feedback uses the shared program/literature-plan.json")
    path = path_in(project, plan_path)
    if expected is not None and sha(path) != expected:
        raise ValueError("stale literature plan; review the current plan")
    plan = read(path)
    if plan.get("schema_version") != "1.0":
        raise ValueError("unsupported literature discovery plan")
    scope = intelligence._scope(project, plan.get("doctoral_question"))
    intelligence._preferences(plan)
    return path, plan, scope


def _sources(project, references):
    if not isinstance(references, list) or not references:
        raise ValueError("feedback needs executed candidate source receipts")
    for reference in references:
        if not isinstance(reference, dict):
            raise ValueError("malformed candidate source receipt")
        for name, digest_name in (("raw_response_path", "response_sha256"),
                                  ("normalized_results_path", "normalized_results_sha256")):
            relative = reference.get(name, "")
            if not isinstance(relative, str) or not relative.startswith("evidence/literature/"):
                raise ValueError("candidate source must be a literature receipt")
            if sha(path_in(project, relative)) != reference.get(digest_name):
                raise ValueError("stale candidate source receipt")


def _document(project, relative, kind):
    path = path_in(project, relative)
    _trusted(project, path)
    value = read(path)
    if value.get("kind") != kind or value.get("content_sha256") != digest({k: v for k, v in value.items() if k != "content_sha256"}):
        raise ValueError("feedback document is stale or tampered")
    return path, value


def _save(project, relative, value):
    value = {**value, "content_sha256": digest(value)}
    path = path_in(project, relative, exists=False)
    if path.is_file():
        _trusted(project, path)
        if read(path) != value:
            raise ValueError("refusing to overwrite an immutable feedback event")
        return value
    write(path, value)
    record(project, [path], MODULE)
    return value


def _bindings(project, supplied):
    if not isinstance(supplied, list) or len(supplied) > 30:
        raise ValueError("feedback evidence needs at most thirty source bindings")
    values = []
    for binding in supplied:
        if not isinstance(binding, dict):
            raise ValueError("feedback evidence needs path/hash/locator objects")
        relative = binding.get("path", "")
        # Reject credentials/control-plane and raw binary material. Outcome
        # records must cite reviewed, readable research evidence or receipts.
        if (not isinstance(relative, str) or not relative.startswith(("literature/", "evidence/literature/", "reports/", "papers/", "experiments/results/", "experiments/runs/"))
                or relative.startswith(ROOT + "/") or any(word in relative.casefold() for word in ("secret", "credential", ".env"))):
            raise ValueError("feedback evidence must bind a research artifact")
        verified = bound_source(project, binding)
        source = path_in(project, relative)
        if source.stat().st_size > 2_000_000:
            raise ValueError("feedback evidence excerpt must use a bounded readable artifact")
        try:
            lines = source.read_text(encoding="utf-8").splitlines()
        except UnicodeError as exc:
            raise ValueError("feedback evidence must use UTF-8 text, not a binary asset") from exc
        start, end = binding.get("start_line"), binding.get("end_line")
        quote = binding.get("quote")
        if (type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines)
                or end - start >= 500 or not isinstance(quote, str) or not 1 <= len(quote.strip()) <= 20000
                or "\n".join(lines[start - 1:end]).strip() != quote.strip()):
            raise ValueError("feedback evidence needs an exact current quote and line range")
        values.append({**verified, "start_line": start, "end_line": end, "quote": quote})
    return values


def _experiment_evidence(project, bindings, paper_ids):
    """A claimed actual use needs a matching successful executor record.

    This verifies occurrence, frozen plan and output identity. It cannot verify
    that the literature improved the experiment or that its result is correct.
    """
    receipts = [row for row in bindings if row["path"].startswith("experiments/runs/") and row["path"].endswith("/run.json")]
    if not receipts:
        raise ValueError("experiment_utility used needs an actual successful executor receipt")
    registry = evidence.read_jsonl(path_in(project, "experiments/registry.jsonl"))
    for binding in receipts:
        entry = read(path_in(project, binding["path"]))
        expected_path = "experiments/runs/" + str(entry.get("attempt_id", "")) + "/run.json"
        if (binding["path"] != expected_path or entry not in registry or entry.get("status") != "succeeded"
                or entry.get("paper_id") not in paper_ids or not entry.get("input_integrity", {}).get("passed")
                or not re.fullmatch(r"[a-f0-9]{64}", str(entry.get("approved_plan_sha256", "")))
                or not entry.get("outputs")):
            raise ValueError("experiment-use feedback needs a successful registered same-paper executor receipt")
        for output in entry["outputs"]:
            if sha(path_in(project, output.get("path", ""))) != output.get("sha256"):
                raise ValueError("experiment-use output is missing or stale")


def record_feedback(project: Path, feedback: dict, *, expected_leads_sha256: str,
                    plan_path=intelligence.PLAN, leads_path=intelligence.OUTPUT) -> dict:
    """Record one observed outcome; same ID+payload is idempotent, edits fail."""
    _cloud()
    project = Path(project).resolve()
    plan_file, plan, scope = _plan(project, plan_path)
    if leads_path != intelligence.OUTPUT:
        raise ValueError("feedback uses current executed topic-leads.json")
    leads_file = path_in(project, leads_path)
    if sha(leads_file) != expected_leads_sha256:
        raise ValueError("stale discovery report")
    _trusted(project, leads_file)
    leads = read(leads_file)
    if (leads.get("kind") != "literature_discovery_intelligence" or
            leads.get("plan") != {"path": plan_path, "sha256": sha(plan_file)} or
            leads.get("doctoral_question") != scope["doctoral_question"]):
        raise ValueError("feedback requires discovery from the exact current plan and question")
    if not isinstance(feedback, dict):
        raise ValueError("feedback must be an explicit observation object")
    allowed = {"event_id", "candidate_id", "candidate_sha256", "sources_sha256", "recorded_by", "recorded_at",
               "reason", "outcomes", "evidence", "suggested_keywords", "paper_ids", "related_candidate_id"}
    if set(feedback) - allowed:
        raise ValueError("unknown feedback fields")
    event_id = _id(feedback.get("event_id"))
    candidate = next((row for row in leads.get("candidates", []) if row.get("canonical_id") == feedback.get("candidate_id")), None)
    if candidate is None or digest(candidate) != feedback.get("candidate_sha256"):
        raise ValueError("feedback candidate is missing or stale")
    sources = candidate.get("source_refs", [])
    _sources(project, sources)
    if feedback.get("sources_sha256") != digest(sources):
        raise ValueError("feedback source bindings are stale")
    outcomes = feedback.get("outcomes")
    if not isinstance(outcomes, dict) or set(outcomes) != set(OUTCOMES):
        raise ValueError("all five reading outcome dimensions are required; use unknown/not_evaluated when unobserved")
    if any(not isinstance(value, str) or value not in OUTCOMES[name] for name, value in outcomes.items()):
        raise ValueError("invalid reading outcome value")
    stamp = _text(feedback.get("recorded_at"), "recorded_at", 80)
    try:
        timestamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if timestamp.tzinfo is None or timestamp > datetime.now(timezone.utc):
            raise ValueError("timestamp is missing a timezone or is in the future")
    except ValueError as exc:
        raise ValueError("feedback needs an actual timezone-aware recorded_at") from exc
    bindings = _bindings(project, feedback.get("evidence", []))
    if not bindings and (outcomes["evidence_sufficiency"] != "unknown" or
                         outcomes["experiment_utility"] in {"used", "not_useful"} or
                         outcomes["source_accessibility"] != "unknown"):
        raise ValueError("observed evidence/access/experiment outcomes need source-bound evidence")
    related = feedback.get("related_candidate_id")
    if outcomes["duplicates"] in {"duplicate", "version"}:
        other = next((row for row in leads["candidates"] if row.get("canonical_id") == related), None)
        if not other or related == candidate["canonical_id"]:
            raise ValueError("duplicate/version feedback needs a distinct current related candidate")
        _sources(project, other.get("source_refs", []))
        related = {"candidate_id": related, "candidate_sha256": digest(other), "source_refs": other["source_refs"]}
    elif related is not None:
        raise ValueError("related candidate is only accepted for duplicate/version observations")
    papers = feedback.get("paper_ids", [])
    if (not isinstance(papers, list) or any(not isinstance(value, str) for value in papers)
            or len(set(papers)) != len(papers) or any(value not in {f"P{i:02}" for i in range(1, 7)} for value in papers)):
        raise ValueError("feedback scope needs distinct P01-P06 paper IDs")
    if outcomes["experiment_utility"] == "used":
        _experiment_evidence(project, bindings, papers)
    keywords = intelligence._keywords(feedback.get("suggested_keywords", []), "suggested_keywords")
    value = {"schema_version": "1.0", "kind": "literature_reading_feedback", "event_id": event_id,
             "plan": {"path": plan_path, "sha256": sha(plan_file)}, "scope": scope,
             "discovery": {"path": leads_path, "sha256": expected_leads_sha256},
             "candidate_id": candidate["canonical_id"], "candidate_sha256": digest(candidate),
             "source_refs": sources, "sources_sha256": digest(sources), "related_candidate": related,
             "recorded_by": _text(feedback.get("recorded_by"), "recorded_by", 200), "recorded_at": stamp,
             "reason": _text(feedback.get("reason"), "reason"), "outcomes": outcomes,
             "evidence": bindings, "suggested_keywords": keywords, "paper_ids": sorted(papers),
             "scientific_inclusion_decided": False, "claim_support_verified": False,
             "gate_approved": False, "paid_model_calls": 0}
    return _save(project, f"{ROOT}/events/{event_id}.json", value)


def _events(project, event_ids, plan_hash):
    if (not isinstance(event_ids, list) or not 1 <= len(event_ids) <= 200
            or any(not isinstance(value, str) for value in event_ids) or len(set(event_ids)) != len(event_ids)):
        raise ValueError("select 1..200 distinct feedback event IDs")
    events = []
    for identifier in sorted(event_ids):
        path, event = _document(project, f"{ROOT}/events/{_id(identifier)}.json", "literature_reading_feedback")
        if event.get("plan", {}).get("sha256") != plan_hash:
            raise ValueError("feedback batch is stale for the current plan")
        _sources(project, event["source_refs"])
        if event.get("related_candidate"):
            _sources(project, event["related_candidate"]["source_refs"])
        _bindings(project, event["evidence"])
        if event["outcomes"]["experiment_utility"] == "used":
            _experiment_evidence(project, event["evidence"], event["paper_ids"])
        events.append({"path": path.relative_to(project).as_posix(), "sha256": sha(path), "event": event})
    return events


def _reviews(project):
    directory = path_in(project, f"{ROOT}/reviews/placeholder.json", exists=False).parent
    if not directory.exists():
        return []
    return [_document(project, path.relative_to(project).as_posix(), "literature_feedback_review")[1]
            for path in sorted(directory.glob("*.json"))]


def _unused(project, event_ids):
    used = {identifier for row in _reviews(project) if row.get("decision") == "adopt" for identifier in row.get("event_ids", [])}
    if used.intersection(event_ids):
        raise ValueError("feedback event was already adopted; do not learn twice from the same observations")


def propose(project: Path, *, event_ids: list[str], expected_plan_sha256: str,
            proposal: dict | None = None, plan_path=intelligence.PLAN) -> dict:
    """Prepare an auditable before/after proposal; never write the plan here.

    Optional externally authored proposals use {topic_keywords_add: [],
    ranking_weights: {}, rationale: str, provenance: [{path,sha256,locator}]}.
    External model plans stay read-only inputs; this deterministic operation
    independently validates and writes only the administrative proposal.
    """
    _cloud()
    project = Path(project).resolve()
    plan_file, plan, scope = _plan(project, plan_path, expected_plan_sha256)
    events = _events(project, event_ids, expected_plan_sha256)
    _unused(project, event_ids)
    before = {key: intelligence._preferences(plan)[key] for key in ("topic_keywords", "ranking_weights")}
    after = deepcopy(before)
    suggestions, rationale, origin = [], [], {"kind": "deterministic_outcome_rules", "paid_model_calls": 0}
    values = [row["event"] for row in events]
    for row in values:
        outcome = row["outcomes"]
        if outcome["relevance"] == "irrelevant":
            suggestions.append({"action": "inspect_query_precision", "candidate_id": row["candidate_id"], "event_id": row["event_id"]})
        if outcome["duplicates"] in {"duplicate", "version"}:
            suggestions.append({"action": "review_canonical_identity_or_version", "candidate_id": row["candidate_id"], "event_id": row["event_id"]})
        if outcome["source_accessibility"] in {"blocked", "missing"}:
            suggestions.append({"action": "review_authorized_alternative_source", "candidate_id": row["candidate_id"], "event_id": row["event_id"]})
        if outcome["evidence_sufficiency"] in {"partial", "insufficient"}:
            suggestions.append({"action": "retrieve_fulltext_and_adjacent_counterevidence", "candidate_id": row["candidate_id"], "event_id": row["event_id"]})
        if outcome["experiment_utility"] in {"used", "promising", "not_useful"}:
            suggestions.append({"action": "inspect_experiment_transfer_conditions", "candidate_id": row["candidate_id"], "event_id": row["event_id"]})
    # Increase precision only; access failures, contrary findings and poor
    # experimental transfer never lower scientific inclusion or source scores.
    if sum(row["outcomes"]["relevance"] == "irrelevant" for row in values) * 2 > len(values):
        after["ranking_weights"]["topic_relevance"] = min(10, after["ranking_weights"]["topic_relevance"] + 0.5)
        rationale.append("Most reviewed retrievals were irrelevant; propose a bounded relevance-weight increase.")
    if any(row["outcomes"]["evidence_sufficiency"] in {"partial", "insufficient"} for row in values):
        after["ranking_weights"]["abstract_rhetoric"] = max(0, after["ranking_weights"]["abstract_rhetoric"] - 0.25)
        rationale.append("Insufficient located evidence warrants less reliance on abstract rhetoric, not exclusion of contrary work.")
    additions = sorted({word for row in values if row["outcomes"]["relevance"] != "irrelevant" for word in row["suggested_keywords"]}, key=str.casefold)
    if proposal is not None:
        if not isinstance(proposal, dict) or set(proposal) - {"topic_keywords_add", "ranking_weights", "rationale", "provenance"}:
            raise ValueError("external proposals may only add keywords and adjust discovery weights")
        rationale = [_text(proposal.get("rationale"), "external proposal rationale")]
        provenance = _bindings(project, proposal.get("provenance", []))
        if not provenance:
            raise ValueError("external proposals require current read-only proposal provenance")
        additions = intelligence._keywords(proposal.get("topic_keywords_add", []), "topic_keywords_add")
        external_weights = proposal.get("ranking_weights", {})
        if not isinstance(external_weights, dict):
            raise ValueError("external ranking weights must be an explicit object")
        after["ranking_weights"].update(external_weights)
        origin = {"kind": "validated_external_read_only_suggestion", "provenance": provenance, "paid_model_calls": 0}
    after["topic_keywords"] = intelligence._keywords([*before["topic_keywords"], *additions], "topic_keywords", required=True)
    intelligence._preferences({**plan, **after})
    payload = {"schema_version": "1.0", "kind": "literature_feedback_proposal",
               "plan": {"path": plan_path, "sha256": sha(plan_file)}, "scope": scope,
               "event_ids": sorted(event_ids), "events": [{"path": row["path"], "sha256": row["sha256"]} for row in events],
               "batch_sha256": digest(sorted(event_ids)), "before": before, "after": after,
               "configuration_changes": before != after, "operational_suggestions": suggestions,
               "rationale": rationale or ["Retain discovery preferences and inspect the recorded operational follow-ups."],
               "origin": origin, "impacted_scope": {"candidate_ids": sorted({row["candidate_id"] for row in values}),
                   "paper_ids": sorted({paper for row in values for paper in row["paper_ids"]}),
                   "doctoral_question_changed": False, "scientific_records_changed": False},
               "status": "pending_explicit_review", "automatic_adoption": False, "gate_approved": False,
               "scientific_quality_verified": False, "paid_model_calls": 0}
    payload["proposal_id"] = "proposal-" + digest(payload)[:32]
    return _save(project, f"{ROOT}/proposals/{payload['proposal_id']}.json", payload)


def review(project: Path, proposal_id: str, *, expected_proposal_sha256: str,
           expected_plan_sha256: str, decision: str, reviewed_by: str, reason: str,
           authorization: str, owner_authorization: dict | None = None, plan_path=intelligence.PLAN) -> dict:
    """Adopt/reject only from a trusted owner-review route, never a model queue.

    The caller must authenticate the owner or independently validate the named
    manager's delegated authority before supplying owner_authorization with the
    authenticated actor, source_issue_id and exact request_sha256. This proof
    must be constructed by the control plane, never taken from operation JSON.
    """
    _cloud()
    if (not isinstance(owner_authorization, dict) or authorization not in {"human", "authorized_project_manager"}
            or set(owner_authorization) != {"actor", "source_issue_id", "request_sha256"}
            or owner_authorization.get("actor") != reviewed_by
            or not str(owner_authorization.get("source_issue_id", "")).isdigit()
            or int(owner_authorization.get("source_issue_id", 0)) <= 0
            or not re.fullmatch(r"[a-f0-9]{64}", str(owner_authorization.get("request_sha256", "")))):
        raise ValueError("feedback adoption requires an authenticated owner/delegated-manager review route")
    if decision not in {"adopt", "reject"}:
        raise ValueError("review decision must be adopt or reject")
    reviewer = _text(reviewed_by, "reviewed_by", 200)
    note = _text(reason, "review reason")
    project = Path(project).resolve()
    proposal_file, proposed = _document(project, f"{ROOT}/proposals/{_id(proposal_id)}.json", "literature_feedback_proposal")
    existing_review = path_in(project, f"{ROOT}/reviews/{proposal_id}.json", exists=False)
    if existing_review.is_file():
        _, previous = _document(project, existing_review.relative_to(project).as_posix(), "literature_feedback_review")
        if (previous.get("proposal", {}).get("sha256") != expected_proposal_sha256 or previous.get("decision") != decision
                or previous.get("reviewed_by") != reviewer or previous.get("reason") != note
                or previous.get("authorization") != authorization or previous.get("owner_authorization") != owner_authorization
                or previous.get("plan", {}).get("sha256") != expected_plan_sha256):
            raise ValueError("proposal already has a different immutable review decision")
        plan_file, current, scope = _plan(project, plan_path)
        if scope != previous["scope"] or proposed["scope"] != scope or sha(proposal_file) != expected_proposal_sha256:
            raise ValueError("stale proposal or doctoral scope")
        if current == previous["plan_after"]:
            return {**previous, "plan_sha256_after": sha(plan_file), "applied": decision == "adopt", "replayed": True}
        if sha(plan_file) != expected_plan_sha256 or current != previous["plan_before"]:
            raise ValueError("review recovery refuses a plan changed by other work")
        _events(project, proposed["event_ids"], expected_plan_sha256)
        write(plan_file, previous["plan_after"])
        record(project, [plan_file], MODULE)
        return {**previous, "plan_sha256_after": sha(plan_file), "applied": decision == "adopt", "recovered": True}
    plan_file, plan, scope = _plan(project, plan_path, expected_plan_sha256)
    if sha(proposal_file) != expected_proposal_sha256 or proposed["plan"]["sha256"] != expected_plan_sha256 or proposed["scope"] != scope:
        raise ValueError("stale proposal or doctoral scope; prepare and review a current proposal")
    events = _events(project, proposed["event_ids"], expected_plan_sha256)
    if [{"path": row["path"], "sha256": row["sha256"]} for row in events] != proposed["events"]:
        raise ValueError("proposal feedback bindings changed")
    if proposed["origin"].get("provenance"):
        _bindings(project, proposed["origin"]["provenance"])
    _unused(project, proposed["event_ids"])
    actual_before = {key: intelligence._preferences(plan)[key] for key in ("topic_keywords", "ranking_weights")}
    if proposed["before"] != actual_before:
        raise ValueError("proposal preferences no longer match the current plan")
    after = proposed["after"]
    if set(after) != {"topic_keywords", "ranking_weights"} or not set(actual_before["topic_keywords"]).issubset(after["topic_keywords"]):
        raise ValueError("feedback adoption cannot remove topic keywords or alter other controls")
    updated = {**plan, **after} if proposed["configuration_changes"] else deepcopy(plan)
    intelligence._preferences(updated)
    # Persist a recoverable immutable before-image and intent first. A failure
    # cannot produce an unrecorded plan edit or a second adoption of the batch.
    value = {"schema_version": "1.0", "kind": "literature_feedback_review", "proposal_id": proposal_id,
             "proposal": {"path": proposal_file.relative_to(project).as_posix(), "sha256": expected_proposal_sha256},
             "event_ids": proposed["event_ids"], "decision": decision, "reviewed_by": reviewer,
             "reason": note, "authorization": authorization, "reviewed_at": evidence.utc_now(),
             "owner_authorization": owner_authorization,
             "plan": {"path": plan_path, "sha256": expected_plan_sha256},
             "plan_before": plan, "plan_after": updated if decision == "adopt" else plan,
             "scope": scope, "gate_approved": False, "budget_authorized": False,
             "scientific_inclusion_decided": False, "paid_model_calls": 0}
    value = _save(project, f"{ROOT}/reviews/{proposal_id}.json", value)
    if decision == "adopt":
        write(plan_file, updated)
        record(project, [plan_file], MODULE)
    return {**value, "plan_sha256_after": sha(plan_file), "applied": decision == "adopt"}
