"""Source-bound semantic reading plans, progress and experiment/topic dossiers.

The deterministic layer arranges located statements and writer-authored semantic
objectives; it does not infer novelty from word overlap or execute experiments.
Existing authorized scientific writers can supply explicit objectives/candidates
in program/literature-reasoning.json. No network or model call occurs here.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import itertools
import json
from pathlib import Path
import re

from scripts.research_artifacts import record, sha, write

EXTENDED_FIELDS = (
    "hypotheses", "competing_explanations", "assumptions", "datasets", "protocols",
    "negative_controls", "robustness", "statistics", "compute_budget", "resources",
    "comparability", "contradictions", "discriminating_tests", "falsification",
    "thesis_contribution",
)
CONFIG = "program/literature-reasoning.json"
PROGRESS = "program/literature-progress.json"
PHASES = (
    ("problem", ("research_question", "contributions"),
     "Establish the problem, claimed contribution and connection to the doctoral question.",
     "What exact problem and contribution does this source claim, and why does it matter to the reading question?"),
    ("mechanism", ("methods", "assumptions", "hypotheses", "competing_explanations"),
     "Identify the mechanism and conditions required before comparing outcomes.",
     "Which mechanism and assumptions connect the reported method to its prediction, and what rival explanation remains?"),
    ("protocol", ("baseline", "datasets", "splits", "metrics", "protocols", "statistics", "resources", "compute_budget"),
     "Recover the executable comparison conditions before transferring a result.",
     "Under which data, split, baseline, metric, statistical and compute conditions was the comparison made?"),
    ("challenge", ("counterevidence", "contradictions", "limitations", "findings"),
     "Challenge the current interpretation with located contrary evidence and boundaries.",
     "Which observed result or stated limitation restricts the mechanism, and are contrary findings comparable?"),
    ("test", ("ablations", "negative_controls", "robustness", "discriminating_tests", "falsification"),
     "Design the next falsifiable comparison rather than treating a reported limitation as a research gap.",
     "Which controlled comparison separates the proposed mechanism from its strongest rival, and what outcome would refute it?"),
)
EXPERIMENT_AXES = (
    "research_question", "hypotheses", "competing_explanations", "assumptions",
    "baseline", "datasets", "splits", "metrics", "protocols", "ablations",
    "negative_controls", "robustness", "statistics", "compute_budget", "resources",
    "comparability", "contradictions", "discriminating_tests", "falsification",
    "thesis_contribution",
)
RESOLUTIONS = {
    "research_question": "State the bounded question and its contribution to the same doctoral question.",
    "hypotheses": "Specify a falsifiable mechanism and directional or quantitative prediction.",
    "competing_explanations": "Specify at least two plausible rivals and predictions that differ from the main hypothesis.",
    "assumptions": "Locate identifiability, measurement and applicability assumptions and a way to test each.",
    "baseline": "Identify exact closest-work versions, code revisions and justified comparator settings.",
    "datasets": "Resolve dataset version, license, access, independent unit and leakage risk through existing approvals.",
    "splits": "Specify disjoint train/validation/test units, time boundaries and leakage checks.",
    "metrics": "Specify primary/secondary outcomes, direction, practical threshold and uncertainty.",
    "protocols": "Specify the executable preprocessing, fitting, tuning and evaluation sequence.",
    "ablations": "Isolate each proposed component under matched data, tuning and compute conditions.",
    "negative_controls": "Select controls that should not carry the proposed signal and define failure decisions.",
    "robustness": "Predeclare relevant shifts, seeds and perturbations; retain every registered outcome.",
    "statistics": "Specify independent units, sample size rationale, uncertainty, multiplicity and missing-data handling.",
    "compute_budget": "Estimate runner, memory, runtime, repeat count and approved cost ceiling before G3 execution.",
    "resources": "Resolve code revision, dependencies, data/model access and reproducible cloud feasibility.",
    "comparability": "Audit units, dataset/splits, metrics, tuning, compute and inference scope pair by pair.",
    "contradictions": "Locate disconfirming and adjacent evidence; distinguish disagreement from incompatible protocols.",
    "discriminating_tests": "State main and rival predictions, controlled intervention and explicit decision conditions.",
    "falsification": "State the outcome that would reject or narrow the proposed claim before final runs.",
    "thesis_contribution": "Map standalone value and cumulative contribution to P01-P06 under one doctoral question.",
}
OUTCOMES = {"supports", "contradicts", "insufficient", "unclear"}


def _wb():
    from scripts import literature_workbench
    return literature_workbench


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def _keys(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(label + " has unsupported fields or is not an object")


def _text(value, label, maximum=6000):
    return _wb()._text(value, label, maximum)


def _load(project, relative, default):
    relative = str(relative)
    if not relative.startswith("program/") or len(Path(relative).parts) != 2 or not relative.endswith(".json"):
        raise ValueError("reasoning/progress input must be a JSON file directly under program/")
    path = _wb()._path(project, relative, exists=False)
    if not path.exists():
        return default, None
    if path.stat().st_size > 2_000_000:
        raise ValueError("reasoning/progress input exceeds 2 MB")
    from scripts.output_provenance import current_origin
    if current_origin(project, path).get("family") == "anthropic":
        raise ValueError("persistent reasoning/progress may not have a Claude writer")
    result = _wb()._json(path.read_bytes())
    if not isinstance(result, dict) or result.get("schema_version") != "1.0":
        raise ValueError("unsupported literature reasoning/progress schema")
    return result, {"path": relative, "sha256": sha(path)}


def _evidence(project, values, papers):
    if not isinstance(values, list) or not 1 <= len(values) <= 30:
        raise ValueError("semantic statements require 1..30 located evidence anchors")
    result = []
    for item in values:
        if (not isinstance(item, dict) or not isinstance(item.get("paper_id"), str)
                or item["paper_id"] not in papers):
            raise ValueError("reasoning evidence references an unknown or out-of-scope library paper")
        paper = papers[item["paper_id"]]
        if paper.get("status") != "current":
            raise ValueError("reasoning refuses stale or invalid paper evidence")
        result.append({"paper_id": paper["id"], **_wb().validate_anchor(
            project, paper, {key: val for key, val in item.items() if key != "paper_id"})})
    return result


def _statement(project, row, papers):
    _keys(row, {"text", "kind", "evidence", "inference_boundary"}, "semantic statement")
    kind = row.get("kind")
    if not isinstance(kind, str) or kind not in {"author_claim", "model_inference", "human_interpretation"}:
        raise ValueError("semantic statements must distinguish source claims and interpretations")
    bound = _evidence(project, row.get("evidence"), papers)
    if kind == "author_claim" and any(a["path"] not in {
            papers[a["paper_id"]]["source"]["path"],
            (papers[a["paper_id"]].get("reader") or {}).get("path")} for a in bound):
        raise ValueError("author claims must cite original source text")
    return {"text": _text(row.get("text"), "semantic statement"), "kind": kind,
            "evidence": bound, "inference_boundary": (
                _text(row.get("inference_boundary"), "interpretation inference boundary")
                if kind != "author_claim" else row.get("inference_boundary")),
            "semantic_verification": False}


def _config(project, library, reasoning_path=None):
    value, binding = _load(project, reasoning_path or CONFIG,
                           {"schema_version": "1.0", "reading_objectives": [], "experiment_candidates": []})
    _keys(value, {"schema_version", "doctoral_question", "reading_objectives", "experiment_candidates"}, "reasoning config")
    scope = library.get("scope", {}).get("doctoral_question")
    question = value.get("doctoral_question")
    if question is not None:
        _text(question, "reasoning doctoral question", 4000)
        if scope and question.strip() != scope.strip():
            raise ValueError("reasoning differs from the current workbench doctoral question")
    papers = {p["id"]: p for p in library["papers"]}
    objectives, candidates, seen = [], [], set()
    for name, maximum in (("reading_objectives", 1000), ("experiment_candidates", 50)):
        rows = value.get(name, [])
        if not isinstance(rows, list) or len(rows) > maximum:
            raise ValueError(name + " exceeds its bounded item limit")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(name + " entries must be objects")
            identifier = _wb()._id(row.get("id"), "reasoning ID")
            if (name, identifier) in seen:
                raise ValueError("duplicate reasoning ID")
            seen.add((name, identifier))
            if name == "reading_objectives":
                _keys(row, {"id", "paper_id", "question", "purpose", "field", "evidence"}, "reading objective")
                owner = row.get("paper_id")
                if not isinstance(owner, str) or owner not in papers:
                    raise ValueError("reading objective references an unknown paper")
                if not isinstance(row.get("field"), str) or row["field"] not in set(_wb().FIELDS) | set(EXTENDED_FIELDS):
                    raise ValueError("reading objective field is unsupported")
                objectives.append({"id": identifier, "paper_id": owner,
                    "question": _text(row.get("question"), "reading objective question"),
                    "purpose": _text(row.get("purpose"), "reading objective purpose"),
                    "field": row["field"], "evidence": _evidence(project, row.get("evidence"), {owner: papers[owner]})})
            else:
                _keys(row, {"id", "question", "source_paper_ids", "paper_ids", "fields", "nearest_work_ids"}, "experiment candidate")
                source_ids = row.get("source_paper_ids")
                if (not isinstance(source_ids, list) or not 1 <= len(source_ids) <= 30
                        or any(not isinstance(i, str) for i in source_ids)
                        or len(set(source_ids)) != len(source_ids) or any(i not in papers for i in source_ids)):
                    raise ValueError("candidate needs distinct current library source IDs")
                targets = row.get("paper_ids", [])
                if (not isinstance(targets, list) or any(not isinstance(i, str) for i in targets)
                        or len(set(targets)) != len(targets)
                        or any(i not in {f"P{i:02d}" for i in range(1, 7)} for i in targets)):
                    raise ValueError("candidate mappings must be distinct P01-P06 IDs")
                nearest = row.get("nearest_work_ids", [])
                if (not isinstance(nearest, list) or any(not isinstance(i, str) for i in nearest)
                        or len(set(nearest)) != len(nearest)
                        or any(i not in source_ids for i in nearest)):
                    raise ValueError("nearest work must be among the candidate's cited sources")
                fields = row.get("fields", {})
                if not isinstance(fields, dict) or set(fields) - set(EXPERIMENT_AXES):
                    raise ValueError("candidate has unsupported experiment fields")
                validated = {}
                for field, entries in fields.items():
                    if not isinstance(entries, list) or len(entries) > 30:
                        raise ValueError("candidate field needs at most 30 statements")
                    validated[field] = [_statement(project, entry, {i: papers[i] for i in source_ids}) for entry in entries]
                candidates.append({"id": identifier, "question": _text(row.get("question"), "candidate question"),
                    "source_paper_ids": source_ids, "nearest_work_ids": nearest, "paper_ids": targets,
                    "fields": validated, "status": "proposal_pending_scientific_review",
                    "novelty_verified": False, "comparability_verified": False,
                    "experiment_executed": False, "gate_approved": False})
    return {"reading_objectives": objectives, "experiment_candidates": candidates}, binding


def _section_rows(project, paper):
    source = paper.get("reader") or paper["source"]
    if paper.get("source_scope") == "metadata_only" or Path(source["path"]).suffix.lower() == ".pdf":
        return []
    lines = _wb()._Files(project).text(source["path"]).splitlines()
    # Native readers also contain translations and generated reading aids. Only
    # original-page ranges may supply a source section or missing-evidence route.
    ranges = [(int(page), bounds[0], bounds[1]) for page, bounds in
              (paper.get("reader") or {}).get("page_ranges", {}).items()]
    if not ranges:
        ranges = [(None, 1, len(lines))] if lines else []
    sections = []
    for page, first, last in sorted(ranges, key=lambda value: value[1]):
        start, title, level = first, f"Original text, PDF page {page}" if page else "Unsectioned source text", 0
        for n in range(first, last + 1):
            stripped = lines[n - 1].strip()
            match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            numbered = re.match(r"^(\d+(?:\.\d+)*\.?)[ \t]+([A-Z][^.!?]{1,100})$", stripped)
            named = stripped.casefold() in {"abstract", "introduction", "methods", "methodology", "results", "discussion", "conclusion", "conclusions", "limitations", "references"}
            if match or numbered or named:
                if n > start:
                    sections.append({"title": title, "level": level, "start_line": start, "end_line": n - 1, "pdf_page": page})
                start, title, level = n, match.group(2) if match else stripped, len(match.group(1)) if match else 1
        sections.append({"title": title, "level": level, "start_line": start, "end_line": last, "pdf_page": page})
    return [{**row, "path": source["path"], "sha256": source["sha256"],
             "structure_detection": "source_heading_not_semantic_verification"} for row in sections]


def _located_sections(anchors, sections):
    result = []
    for anchor in anchors:
        matching = [s for s in sections if s["path"] == anchor["path"]
                    and s["start_line"] <= anchor["start_line"] <= s["end_line"]]
        result.append({**anchor, "section": matching[-1] if matching else None})
    return result


def _card_rows(paper, fields):
    rows = []
    for field in fields:
        for statement in paper["card"].get("fields", {}).get(field, []):
            rows.append({"field": field, **statement,
                         "evidence": [{"paper_id": paper["id"], **a} for a in statement["evidence"]]})
    return rows


def _step(paper, phase, fields, purpose, question, sections, *, objective=None):
    rows = _card_rows(paper, fields)
    anchors = [a for r in rows for a in r["evidence"]]
    if objective:
        anchors = objective["evidence"]
    identifier = paper["id"] + "-" + ("objective-" + objective["id"] if objective else phase)
    located = _located_sections(anchors, sections)
    statement_questions = [f"For the located {r['field']} statement, what evidence establishes or limits: {r['text']}"
                           for r in rows[:3]]
    result = {"id": identifier, "step_id": identifier, "paper_id": paper["id"], "title": paper["title"],
              "phase": phase, "purpose": purpose, "question": question,
              "questions": [question, *statement_questions], "target_fields": list(fields),
              "reported_statements": rows, "start_here": located,
              "unknown_fields": [f for f in _wb().FIELDS if not paper["card"].get("fields", {}).get(f)],
              "phase_missing_fields": [f for f in fields if not paper["card"].get("fields", {}).get(f)],
              "scope": paper.get("read_scope"), "source": paper["source"],
              "status": "ready_to_read" if anchors else "needs_source_reading",
              "semantic_verification": False, "dependencies": []}
    if not anchors:
        result["missing_evidence_action"] = (
            "Acquire an authorized full-text reader and locate these fields; do not infer absence from a missing card entry."
            if paper.get("source_scope") == "metadata_only" else
            "Read the exact source sections and add located statements for the missing fields.")
        result["section_candidates"] = sections
    result["step_sha256"] = _digest(result)
    return result


def _time(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("recorded_at must be an ISO timestamp with timezone") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("recorded_at requires a timezone")
    return value


def _progress(project, papers, question, steps, progress_path):
    progress, binding = _load(project, progress_path or PROGRESS, {"schema_version": "1.0", "events": []})
    _keys(progress, {"schema_version", "events"}, "reading progress")
    events = progress.get("events", [])
    if not isinstance(events, list) or len(events) > 10000:
        raise ValueError("reading progress requires at most 10000 append-only events")
    if events:
        from scripts.output_provenance import current_origin
        origin = current_origin(project, _wb()._path(project, progress_path or PROGRESS))
        if (origin.get("status") != "tracked" or origin.get("family") != "other"
                or origin.get("model") != "scripts/literature_reasoning.py"):
            raise ValueError("reading progress requires current controlled append-only provenance")
    latest, question_hash = {}, _digest(question)
    step_by_id = {s["id"]: s for s in steps}
    for number, event in enumerate(events):
        _keys(event, {"question_sha256", "step_id", "step_sha256", "answer", "outcome", "evidence", "recorded_by",
                      "recorded_at", "kind", "inference_boundary", "event_id"}, "progress event")
        if event.get("question_sha256") != question_hash or event.get("step_id") not in step_by_id:
            continue
        owner = step_by_id[event["step_id"]]["paper_id"]
        if not isinstance(event.get("outcome"), str) or event["outcome"] not in OUTCOMES:
            raise ValueError("unknown reading answer outcome")
        validated = _statement(project, {"text": event.get("answer"), "kind": event.get("kind"),
            "evidence": event.get("evidence"), "inference_boundary": event.get("inference_boundary")}, {owner: papers[owner]})
        _text(event.get("recorded_by"), "reading answer recorder", 200)
        _time(event.get("recorded_at"))
        latest[event["step_id"]] = {**event, "validated_answer": validated,
            "event_number": number + 1, "current_step_binding": event.get("step_sha256") == step_by_id[event["step_id"]]["step_sha256"]}
    for step in steps:
        answer = latest.get(step["id"])
        if not answer:
            continue
        step["recorded_answer"] = answer
        if not answer["current_step_binding"]:
            step["status"] = "changed_question_or_evidence_requires_recheck"
            continue
        step["status"] = "answer_recorded_pending_semantic_review"
        if answer["outcome"] == "contradicts":
            step["next_missing_evidence"] = "Locate an independent contrary source and audit comparison conditions; revise the interpretation if it survives."
        elif answer["outcome"] == "supports":
            step["next_missing_evidence"] = "Test the strongest rival explanation under matched conditions; a supporting passage does not close the question."
        elif answer["outcome"] == "insufficient":
            step["next_missing_evidence"] = "Obtain the missing full-text protocol, data/code or supplementary evidence before transferring the claim."
        else:
            step["next_missing_evidence"] = "Resolve ambiguous definitions, units or assumptions at the cited source location before choosing a test."
        step["adaptive_question"] = ("The recorded answer is: " + answer["answer"] +
                                     " What specific additional evidence would change that assessment?")
    return binding


def itinerary(project: Path, question: str, *, topic_id=None, paper_id=None, limit=8,
              output_dir=None, reasoning_path=None, progress_path=None) -> dict:
    """Build section-aware, multi-phase plans; validated objectives override lexical ranking.

    limit bounds papers, not reasoning steps. All phases of each selected source
    remain visible, including missing counterevidence and protocol information.
    """
    project = Path(project).resolve()
    _text(question, "reading question")
    if type(limit) is not int or not 1 <= limit <= 30:
        raise ValueError("itinerary limit must be 1..30 papers")
    library, _, manifest = _wb()._snapshot(project, output_dir)
    config, binding = _config(project, library, reasoning_path)
    papers = {p["id"]: p for p in library["papers"] if p["status"] == "current"}
    eligible = {i: p for i, p in papers.items() if (topic_id is None or p.get("topic_id") == topic_id)
                and (paper_id is None or paper_id in p.get("paper_ids", []))}
    hits = _wb().search(project, question, topic_id=topic_id, paper_id=paper_id, limit=100, output_dir=output_dir)
    scores = {}
    for row in hits["results"]:
        scores[row["paper_id"]] = max(scores.get(row["paper_id"], 0), row["score"])
    objective_owners = {o["paper_id"] for o in config["reading_objectives"]}
    # Explicit semantic objectives and mapped contrary evidence outrank keyword
    # scores. Without a lexical match the bounded source set is still readable.
    ordered = sorted(eligible, key=lambda i: (i not in objective_owners,
        not bool(_card_rows(eligible[i], ("counterevidence", "contradictions"))), -scores.get(i, 0), i))[:limit]
    steps = []
    for identifier in ordered:
        paper = papers[identifier]
        sections = _section_rows(project, paper)
        previous = None
        phases = list(PHASES)
        if _card_rows(paper, ("counterevidence", "contradictions")):
            phases = [p for p in phases if p[0] == "challenge"] + [p for p in phases if p[0] != "challenge"]
        for phase, fields, purpose, prompt in phases:
            step = _step(paper, phase, fields, purpose, question + "\n" + prompt, sections)
            # Dependencies are identifiers rather than claims of successful reading.
            step["dependencies"] = [previous] if previous else []
            step["step_sha256"] = _digest({k: v for k, v in step.items() if k != "step_sha256"})
            previous = step["id"]
            steps.append(step)
        for objective in config["reading_objectives"]:
            if objective["paper_id"] == identifier:
                steps.append(_step(paper, "semantic_objective", (objective["field"],), objective["purpose"],
                                   objective["question"], sections, objective=objective))
    progress_binding = _progress(project, papers, question, steps, progress_path)
    unanswered = [s for s in steps if s["status"] != "answer_recorded_pending_semantic_review"]
    next_step = next((s for s in steps if s.get("recorded_answer", {}).get("outcome") == "contradicts"),
                     unanswered[0] if unanswered else None)
    result = {"schema_version": "1.0", "kind": "section_aware_evidence_bound_reading_plan", "question": question,
        "topic_id": topic_id, "paper_id": paper_id, "limit": limit, "selected_paper_ids": ordered,
        "scope": library.get("scope"), "steps": steps, "next_step_id": next_step["id"] if next_step else None,
        "progress": {"total_steps": len(steps), "answered_steps": len(steps) - len(unanswered),
                     "human_full_text_reading_verified": False},
        "inputs": [v for v in (binding, progress_binding) if v], "reasoning_path": reasoning_path or CONFIG,
        "progress_path": progress_path or PROGRESS, "snapshot_sha256": _digest(manifest),
        "implementation_sha256": sha(Path(__file__)), "status": "reading_plan_only" if steps else "no_eligible_sources",
        "selection_method": "explicit_semantic_objectives_then_contrary_evidence_then_lexical_relevance",
        "retrieval_completeness_verified": False, "gate_approved": False,
        "scientific_completion_verified": False, "semantic_verification": False, "model_call_made": False}
    _wb()._save_view(project, output_dir, "itinerary.json", result)
    return result


def record_progress(project: Path, request: dict, *, output_dir=None, progress_path=None) -> dict:
    """Append one exact-source answer to a currently displayed step, then adapt the plan.

    This records an attributed interpretation. It cannot mark a human full-text
    review, approve a scientific gate or certify a source supports an assertion.
    """
    project = Path(project).resolve()
    _keys(request, {"step_id", "expected_step_sha256", "answer", "outcome", "evidence", "recorded_by",
                    "recorded_at", "kind", "inference_boundary"}, "progress request")
    library, _, _ = _wb()._snapshot(project, output_dir)
    relative, _ = _wb()._output(project, output_dir)
    plan = _wb()._json(_wb()._path(project, relative + "/itinerary.json").read_bytes())
    if plan.get("implementation_sha256") != sha(Path(__file__)):
        raise ValueError("reading plan implementation changed; regenerate before recording an answer")
    step = next((s for s in plan.get("steps", []) if s.get("id") == request.get("step_id")), None)
    if step is None or request.get("expected_step_sha256") != step.get("step_sha256"):
        raise ValueError("reading answer needs the exact current step hash")
    if not isinstance(request.get("outcome"), str) or request["outcome"] not in OUTCOMES:
        raise ValueError("unknown reading answer outcome")
    papers = {p["id"]: p for p in library["papers"]}
    _statement(project, {"text": request.get("answer"), "kind": request.get("kind"),
        "evidence": request.get("evidence"), "inference_boundary": request.get("inference_boundary")},
        {step["paper_id"]: papers[step["paper_id"]]})
    _text(request.get("recorded_by"), "reading answer recorder", 200)
    _time(request.get("recorded_at"))
    selected_progress = progress_path or plan.get("progress_path") or PROGRESS
    if not re.fullmatch(r"program/literature-progress(?:-[A-Za-z0-9_-]+)?\.json", str(selected_progress)):
        raise ValueError("progress writes require a dedicated program/literature-progress JSON path")
    progress, _ = _load(project, selected_progress, {"schema_version": "1.0", "events": []})
    _keys(progress, {"schema_version", "events"}, "reading progress")
    if not isinstance(progress.get("events"), list) or len(progress["events"]) >= 10000:
        raise ValueError("reading progress event limit reached")
    # Recompute the current plan without mutating progress: config/source changes
    # may leave a previously displayed step hash obsolete even when sources pass.
    _config(project, library, plan.get("reasoning_path"))
    config_binding = next((i for i in plan.get("inputs", []) if i["path"] == plan.get("reasoning_path")), None)
    config_path = _wb()._path(project, plan.get("reasoning_path", CONFIG), exists=False)
    if bool(config_binding) != config_path.is_file() or (config_binding and sha(config_path) != config_binding["sha256"]):
        raise ValueError("reading objectives changed; regenerate before recording an answer")
    # Validate all active prior events before appending; do not write a new event
    # and only then discover that existing answers contain stale/fabricated text.
    _progress(project, papers, plan["question"], plan.get("steps", []), selected_progress)
    event = {"question_sha256": _digest(plan["question"]), "step_id": step["id"],
             "step_sha256": step["step_sha256"], **{k: v for k, v in request.items() if k != "expected_step_sha256"}}
    event["event_id"] = _digest(event)
    if any(e.get("event_id") == event["event_id"] for e in progress["events"]):
        return {"status": "already_recorded", "event_id": event["event_id"], "model_call_made": False}
    progress["events"].append(event)
    target = _wb()._path(project, selected_progress, exists=False)
    write(target, progress)
    record(project, [target], "scripts/literature_reasoning.py")
    result = itinerary(project, plan["question"], topic_id=plan.get("topic_id"), paper_id=plan.get("paper_id"),
        limit=plan.get("limit", 8), output_dir=output_dir, reasoning_path=plan.get("reasoning_path"), progress_path=selected_progress)
    return {"status": "answer_recorded", "event_id": event["event_id"], "itinerary": result,
            "gate_approved": False, "semantic_verification": False, "model_call_made": False}


def _axis(rows, field):
    statements = [{"paper_id": p["id"], **r} for p in rows for r in p["card"].get("fields", {}).get(field, [])]
    return {"field": field, "statements": statements,
            "status": "located_pending_review" if statements else "missing",
            "required_resolution": RESOLUTIONS[field], "semantic_verification": False}


def comparison_packet(project: Path, paper_ids: list[str], *, question="", output_dir=None, reasoning_path=None) -> dict:
    """Produce complete experiment axes, pairwise audits and falsifiable gap leads.

    Every supplied scientific statement requires exact evidence. Empty axes are
    explicit work items, never filled with guessed methods, numbers or novelty.
    """
    project = Path(project).resolve()
    if (not isinstance(paper_ids, list) or not 1 <= len(paper_ids) <= 30
            or any(not isinstance(i, str) for i in paper_ids)
            or len(set(paper_ids)) != len(paper_ids)):
        raise ValueError("comparison needs 1..30 distinct library paper IDs")
    if question:
        _text(question, "comparison question")
    library, _, manifest = _wb()._snapshot(project, output_dir)
    config, binding = _config(project, library, reasoning_path)
    papers = {p["id"]: p for p in library["papers"]}
    if any(i not in papers for i in paper_ids):
        raise ValueError("comparison references an unknown library paper")
    selected = [papers[i] for i in paper_ids]
    if any(p["status"] != "current" for p in selected):
        raise ValueError("comparison refuses stale or invalid paper evidence")
    rows = [{"paper_id": p["id"], "title": p["title"], "topic_id": p.get("topic_id"), "paper_ids": p["paper_ids"],
             "fields": p["card"]["fields"], "unknown_fields": [f for f in _wb().FIELDS if not p["card"]["fields"].get(f)],
             "experiment_planning_gaps": [f for f in ("baseline", "splits", "metrics", "ablations") if not p["card"]["fields"].get(f)],
             "complete_design_gaps": [f for f in EXPERIMENT_AXES if not p["card"]["fields"].get(f)],
             "source": p["source"], "read_scope": p.get("read_scope"), "semantic_verification": False} for p in selected]
    axes = [_axis(selected, field) for field in EXPERIMENT_AXES]
    comparison_axes = ("datasets", "splits", "metrics", "protocols", "baseline", "statistics", "compute_budget", "assumptions")
    pairs = []
    for a, b in itertools.combinations(selected, 2):
        conditions = []
        for field in comparison_axes:
            left, right = _card_rows(a, (field,)), _card_rows(b, (field,))
            conditions.append({"axis": field, "left": left, "right": right,
                "status": "needs_semantic_comparability_audit" if left and right else "missing_evidence",
                "required_resolution": RESOLUTIONS[field]})
        pairs.append({"left": a["id"], "right": b["id"], "conditions": conditions,
                      "comparability_verified": False, "same_words_do_not_prove_same_protocol": True})
    gap_leads = []
    for p in selected:
        for n, statement in enumerate(_card_rows(p, ("limitations", "counterevidence", "contradictions"))):
            gap_leads.append({"id": p["id"] + "-gap-lead-" + str(n + 1), "source_paper_id": p["id"],
                "reported_boundary": statement, "question": "Under which conditions does this reported boundary persist or disappear?",
                "nearest_work_ids_to_compare": [i for i in paper_ids if i != p["id"]],
                "disconfirmation_search": {"direct": [v for v in (question, statement["text"]) if v],
                    "adjacent": [statement["text"] + " alternative mechanism"],
                    "counterevidence": [statement["text"] + " resolved replication contrary evidence"]},
                "required_next_steps": ["Locate closest and adjacent primary work, including work that may already resolve the boundary.",
                    "Recover comparable protocols and two rival explanations from exact passages.",
                    "Declare a discriminating test and falsification rule before G3 execution."],
                "status": "author_boundary_or_interpretation_not_established_research_gap", "novelty_verified": False})
    candidates = []
    for candidate in config["experiment_candidates"]:
        if not set(candidate["source_paper_ids"]).issubset(paper_ids):
            continue
        fields = candidate["fields"]
        work = [{"field": field, "statements": fields.get(field, []),
                 "status": "proposal_located_pending_review" if fields.get(field) else "missing",
                 "required_resolution": RESOLUTIONS[field]} for field in EXPERIMENT_AXES]
        candidates.append({**candidate, "doctoral_question": library.get("scope", {}).get("doctoral_question"),
            "design_axes": work, "missing_design_fields": [r["field"] for r in work if not r["statements"]],
            "nearest_work_matrix": [r for r in rows if r["paper_id"] in candidate["nearest_work_ids"]],
            "needs_nearest_work_selection": not bool(candidate["nearest_work_ids"]),
            "needs_target_paper_mapping": not bool(candidate["paper_ids"]),
            "readiness": "source_bound_proposal_requires_G1_G3_review"})
    result = {"schema_version": "1.0", "kind": "source_bound_comparison_and_experiment_evidence_packet",
        "question": question, "scope": library.get("scope"), "rows": rows,
        "experiment_design_axes": axes, "pairwise_comparability": pairs, "gap_hypotheses": gap_leads,
        "experiment_candidates": candidates, "missing_semantic_input": not bool(candidates),
        "writer_actions": ["Use existing authorized scientific writer to fill source-bound hypotheses, rivals and test decisions.",
            "Retain unresolved comparison conditions and every contrary result.",
            "Feed reviewed candidates to the existing G1 hypothesis/originality records and G3 protocol; this packet grants no authority."],
        "inputs": [binding] if binding else [], "reasoning_path": reasoning_path or CONFIG,
        "snapshot_sha256": _digest(manifest),
        "implementation_sha256": sha(Path(__file__)), "comparability_verified": False,
        "novelty_verified": False, "experiment_executed": False, "gate_approved": False,
        "scientific_completion_verified": False, "author_claims_are_not_independent_facts": True,
        "model_call_made": False}
    _wb()._save_view(project, output_dir, "comparison.json", result)
    return result
