"""Immutable preparation from native reading, search receipts and notebook records.

No search, acquisition, experiment, model call or scientific decision is made.
Relations and query/evidence associations are declarations pending review.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from scripts import literature_intelligence as intelligence
from scripts import literature_reading as reading
from scripts import literature_reasoning as reasoning
from scripts import literature_workbench as wb
from scripts import research_notebook as notebook
from scripts.output_provenance import current_origin
from scripts.research_artifacts import path_in, read, record, sha, write

MODULE = "scripts/research_frontier.py"
OUTPUT = "reports/research-frontier"
DEFAULT = "program/research-frontier.json"
LEDGER = "evidence/literature-api-ledger.jsonl"
NOTEBOOK = "program/research-notebook.json"
HYPOTHESES = "program/hypothesis-register.json"


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _keys(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(label + " has unsupported fields or is not an object")


def _array(value, label, maximum=100, *, nonempty=False):
    if not isinstance(value, list) or len(value) > maximum or (nonempty and not value):
        raise ValueError(label + " requires a bounded array")
    return value


def _ids(value, label, maximum=100, *, nonempty=False):
    values = _array(value, label, maximum, nonempty=nonempty)
    if any(not isinstance(v, str) or not v.strip() for v in values) or len(set(values)) != len(values):
        raise ValueError(label + " requires distinct nonempty IDs")
    return values


def _origin(project, path, module=None):
    origin = current_origin(project, path)
    if origin.get("family") == "anthropic" or (module and (
            origin.get("status") != "tracked" or origin.get("family") != "other"
            or origin.get("model") != module)):
        raise ValueError("artifact has missing, stale or disallowed provenance: " + str(path))


def _binding(project, relative, bindings, *, optional=False):
    target = path_in(project, relative, exists=not optional)
    value = {"path": relative, "sha256": sha(target) if target.is_file() else None}
    if value not in bindings:
        bindings.append(value)
    if target.is_file():
        _origin(project, target)
    return target


def _bound(project, value, bindings):
    _keys(value, {"path", "sha256"}, "source binding")
    target = _binding(project, value.get("path", ""), bindings)
    if sha(target) != value.get("sha256"):
        raise ValueError("source binding changed: " + value.get("path", ""))
    return target


def _coverage(project, scope, question, papers, bindings):
    target = _bound(project, scope.get("coverage"), bindings)
    if not scope["coverage"]["path"].startswith(reading.OUTPUT + "/coverage-"):
        raise ValueError("frontier coverage must be a native reading coverage report")
    _origin(project, target, "scripts/literature_reading.py")
    report = read(target)
    if (report.get("kind") != "question_scoped_reading_coverage"
            or report.get("question") != question["question"]
            or report.get("implementation_sha256") != sha(Path(reading.__file__))):
        raise ValueError("coverage question or implementation changed; refresh native coverage")
    expected_inputs = []
    for relative in (reasoning.CONFIG, reasoning.PROGRESS):
        _, binding = reasoning._load(project, relative, {"schema_version": "1.0"})
        _binding(project, relative, bindings, optional=True)
        if binding:
            expected_inputs.append(binding)
    if report.get("progress_inputs") != expected_inputs:
        raise ValueError("coverage reasoning/progress changed; refresh native coverage")
    rows = report.get("papers", [])
    if [r.get("paper_id") for r in rows] != scope["paper_ids"]:
        raise ValueError("coverage paper scope differs from the frontier request")
    for row in rows:
        paper = papers[row["paper_id"]]
        if row.get("source") != paper["source"] or row.get("source_scope") != paper.get("source_scope"):
            raise ValueError("coverage source/version changed")
        dimensions = row.get("dimensions", [])
        if [d.get("dimension") for d in dimensions] != scope["dimensions"]:
            raise ValueError("coverage dimensions differ from the frontier request")
        locations = reading._dimension_locations(project, paper)
        for dimension in dimensions:
            if dimension.get("locations") != locations[dimension["dimension"]]:
                raise ValueError("coverage original locations changed")
            for evidence in dimension.get("reusable_evidence", []):
                anchor = dict(evidence["anchor"])
                if anchor.pop("paper_id", None) != paper["id"]:
                    raise ValueError("coverage evidence references another paper")
                wb.validate_anchor(project, paper, anchor)
    return rows


def _ledger(project, bindings):
    target = _binding(project, LEDGER, bindings, optional=True)
    values = []
    if target.is_file():
        for line in target.read_text(encoding="utf-8").splitlines():
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("literature ledger entry must be an object")
                values.append(value)
    indexed, works = {}, {}
    for row in values:
        identity = row.get("receipt_id")
        if not isinstance(identity, str) or not identity or identity in indexed:
            raise ValueError("literature ledger has missing or duplicate receipt IDs")
        indexed[identity] = row
        if row.get("status") == "success":
            actual, refs = intelligence._receipt_works(project, row)
            works[identity] = actual
            for key in ("raw_response_path", "normalized_results_path"):
                _binding(project, refs[key], bindings)
        elif row.get("status") == "failed":
            if row.get("raw_response_path"):
                _bound(project, {"path": row["raw_response_path"], "sha256": row.get("response_sha256")}, bindings)
        else:
            raise ValueError("literature ledger has an unknown attempt status")
    if sum(len(v) for v in works.values()) > 2000:
        raise ValueError("narrow the native literature ledger to a bounded 2000-record frontier scope")
    return values, indexed, works


def _same(left, right):
    return intelligence.canonical_identity(left) == intelligence.canonical_identity(right) or intelligence.canonical_match(left, right)


def _rounds(request, questions, ledger, indexed, works):
    results, seen_rounds, used_receipts, seen_dimensions = [], set(), set(), set()
    positions = {row["receipt_id"]: i for i, row in enumerate(ledger)}
    for entry in _array(request.get("query_rounds", []), "query rounds", 40):
        _keys(entry, {"id", "question_id", "dimension", "receipt_ids", "evidence_ids"}, "query round")
        identity = wb._id(entry.get("id"), "query-round ID")
        if identity in seen_rounds:
            raise ValueError("duplicate query-round ID")
        seen_rounds.add(identity)
        question_id, dimension = entry.get("question_id"), entry.get("dimension")
        if (not isinstance(question_id, str) or question_id not in questions
                or dimension not in questions[question_id]["dimensions"]):
            raise ValueError("query round must reference an actual selected question/dimension")
        receipts = _ids(entry.get("receipt_ids"), "query round receipts", 40, nonempty=True)
        if any(identity not in indexed for identity in receipts):
            raise ValueError("query round references an unexecuted or unknown receipt")
        evidence_ids = _ids(entry.get("evidence_ids", []), "query-round evidence")
        evidence = questions[question_id]["notebook"]["evidence"]
        if not set(evidence_ids).issubset({row["id"] for row in evidence}):
            raise ValueError("query-round evidence IDs must exist in the source-bound notebook")
        ordered = sorted(receipts, key=positions.get)
        actual = [w for identity in ordered for w in works.get(identity, [])]
        canonical = intelligence.deduplicate(actual)
        new = []
        for work in canonical:
            first_receipt = next(row["receipt_id"] for row in ledger if any(
                _same(work, old) for old in works.get(row["receipt_id"], [])))
            if first_receipt in ordered and first_receipt not in used_receipts:
                new.append(work["canonical_id"])
        successes = [indexed[i] for i in ordered if indexed[i]["status"] == "success"]
        failures = [indexed[i] for i in ordered if indexed[i]["status"] == "failed"]
        reused = [identity for identity in ordered if identity in used_receipts]
        # A caller's round label is not evidence that a new dimension was read.
        # Count only a current native answer for this dimension whose original
        # source also backs the referenced notebook observation.
        selected_evidence = [e for e in evidence if e["id"] in evidence_ids]
        covered = [e for p in questions[question_id]["coverage"] for d in p["dimensions"]
                   if d["dimension"] == dimension for e in d.get("reusable_evidence", [])]
        source_matched_ids = [e["id"] for e in selected_evidence if any(
            e["source"]["path"] == a["anchor"]["path"] and e["source"]["sha256"] == a["anchor"]["sha256"]
            for a in covered)]
        attributed = (question_id, dimension) if source_matched_ids and successes else None
        new_dimensions = [dimension] if attributed and attributed not in seen_dimensions else []
        if attributed:
            seen_dimensions.add(attributed)
        has_gaps = bool(questions[question_id]["gaps"])
        advice = "stop_repeating_cached_round" if len(reused) == len(ordered) else (
            "resolve_failed_attempts" if failures else "continue_bounded_reading" if new else
            "reword_or_extend_source_scope" if has_gaps else "stop_this_query_for_review")
        results.append({"id": identity, "question_id": question_id, "dimension": dimension,
            "receipt_ids": ordered, "queries": [{"receipt_id": r["receipt_id"], "provider": r.get("provider"),
                "query": r.get("query"), "status": r["status"], "actual_conditions": r.get("actual_conditions"),
                "result_count": r.get("result_count") if r["status"] == "success" else None,
                "error": r.get("error")} for r in [indexed[i] for i in ordered]],
            "normalized_observation_count": len(actual), "canonical_paper_count": len(canonical),
            "canonical_ids": [w["canonical_id"] for w in canonical], "new_canonical_ids": sorted(new),
            "new_paper_count": len(new), "failed_attempt_count": len(failures),
            "successful_attempt_count": len(successes), "reused_receipt_ids": reused,
            "attributed_evidence_ids": evidence_ids, "source_matched_dimension_evidence_ids": source_matched_ids,
            "new_attributed_evidence_dimensions": new_dimensions,
            "new_attributed_evidence_dimension_count": len(new_dimensions),
            "evidence_round_association": "declared_pending_semantic_review",
            "notebook_locator_overlap_verified": False,
            "advice": advice, "scientific_saturation_verified": False,
            "absence_of_evidence_proven": False})
        used_receipts.update(ordered)
    return results


def _reference(value, questions):
    _keys(value, {"question_id", "kind", "id"}, "notebook reference")
    if (not isinstance(value.get("question_id"), str) or not isinstance(value.get("id"), str)
            or not value["id"].strip()):
        raise ValueError("relation requires existing nonempty notebook IDs")
    question = questions.get(value.get("question_id"))
    kind = value.get("kind")
    if question is None or kind not in {"evidence", "decision"}:
        raise ValueError("relation requires an existing notebook evidence/decision reference")
    rows = question["notebook"]["evidence" if kind == "evidence" else "decisions"]
    row = next((r for r in rows if r.get("id") == value.get("id")), None)
    if row is None:
        raise ValueError("relation references an unknown notebook ID")
    source_ids = [row["id"]] if kind == "evidence" else row["evidence_ids"]
    return {**value, "record_sha256": _digest(row), "source_evidence_ids": source_ids}


def _prepare(project, request_file):
    project = Path(project).resolve()
    bindings = []
    if not isinstance(request_file, str) or not request_file.startswith("program/") or not request_file.endswith(".json"):
        raise ValueError("frontier request must be a JSON file under program/")
    request_path = _binding(project, request_file, bindings)
    request = read(request_path)
    _keys(request, {"schema_version", "kind", "id", "questions", "query_rounds", "proposed_queries", "relations", "max_actions"}, "frontier request")
    if request.get("schema_version") != "1.0" or request.get("kind") != "research_frontier":
        raise ValueError("frontier request requires schema_version 1.0 and kind research_frontier")
    identity = wb._id(request.get("id"), "frontier ID")
    _binding(project, NOTEBOOK, bindings)
    current = notebook.build(project)
    if current["status"] == "blocked":
        raise ValueError("source-bound notebook is blocked: " + "; ".join(current["errors"]))
    by_question = {row["id"]: row for row in current["questions"]}
    library, _, manifest = wb._snapshot(project)
    papers = {p["id"]: p for p in library["papers"] if p.get("status") == "current"}
    for item in [*manifest.get("inputs", []), *manifest.get("outputs", [])]:
        _binding(project, item["path"], bindings)
    _binding(project, wb.OUTPUT + "/manifest.json", bindings)
    hypotheses_path = _binding(project, HYPOTHESES, bindings, optional=True)
    hypothesis_ids = {h.get("hypothesis_id") for h in read(hypotheses_path).get("hypotheses", [])} if hypotheses_path.is_file() else set()
    for relative in ("program/core-thesis.json", "state/run.json"):
        _binding(project, relative, bindings, optional=True)
    questions, worklist = {}, []
    for scope in _array(request.get("questions"), "selected questions", 20, nonempty=True):
        _keys(scope, {"question_id", "paper_ids", "dimensions", "coverage", "hypothesis_ids"}, "question scope")
        question_id = scope.get("question_id")
        if not isinstance(question_id, str) or question_id not in by_question or question_id in questions:
            raise ValueError("frontier needs distinct existing notebook question IDs")
        selected = _ids(scope.get("paper_ids"), "selected paper IDs", 30, nonempty=True)
        dimensions = _ids(scope.get("dimensions"), "selected dimensions", len(reading.DIMENSIONS), nonempty=True)
        if any(p not in papers for p in selected) or any(d not in reading.DIMENSIONS for d in dimensions):
            raise ValueError("frontier needs current native papers and supported reading dimensions")
        hypothesis_links = _ids(scope.get("hypothesis_ids", []), "hypothesis IDs")
        if not set(hypothesis_links).issubset(hypothesis_ids):
            raise ValueError("frontier hypothesis IDs must exist in the native hypothesis register")
        question = by_question[question_id]
        for evidence in question["evidence"]:
            _binding(project, evidence["source"]["path"], bindings)
        rows = _coverage(project, scope, question, papers, bindings)
        gaps = []
        contrary = [e for e in question["evidence"] if e["stance"] in {"contradicts", "mixed"}]
        for row in rows:
            paper = papers[row["paper_id"]]
            for dimension in row["dimensions"]:
                if dimension["dimension"] == "metadata" or dimension.get("reusable_evidence"):
                    continue
                kind = ("fulltext_acquisition" if paper.get("source_scope") == "metadata_only" else
                        "read_original" if dimension["locations"] else "locate_original_dimension")
                gap = {"question_id": question_id, "paper_id": paper["id"], "dimension": dimension["dimension"],
                    "hypothesis_ids": hypothesis_links, "kind": kind, "reason": dimension["next_action"],
                    "source": paper["source"], "locations": dimension["locations"],
                    "reuse_source_id": paper["id"], "new_acquisition_authorized": False}
                gap["gap_id"] = "gap-" + _digest(gap)[:20]
                gaps.append(gap)
        for text in question["missing_evidence"]:
            gap = {"question_id": question_id, "paper_id": None, "dimension": "question_gap",
                "hypothesis_ids": hypothesis_links, "kind": "bounded_discovery", "reason": text,
                "reuse_source_ids": selected, "scientific_gap_proven": False}
            gap["gap_id"] = "gap-" + _digest(gap)[:20]
            gaps.append(gap)
        for evidence in contrary:
            gap = {"question_id": question_id, "dimension": "counterevidence", "hypothesis_ids": hypothesis_links,
                "kind": "compare_contrary_evidence", "evidence_id": evidence["id"], "source": evidence["source"],
                "reason": "Inspect the contrary result and applicability; retain the original observation.",
                "reuse_source_ids": selected, "semantic_support_verified": False}
            gap["gap_id"] = "gap-" + _digest(gap)[:20]
            gaps.insert(0, gap)
        questions[question_id] = {"question_id": question_id, "question": question["question"], "notebook": question,
            "hypothesis_ids": hypothesis_links, "paper_ids": selected, "dimensions": dimensions,
            "coverage": rows, "gaps": gaps, "contrary_evidence_ids": [e["id"] for e in contrary]}
        worklist.extend(gaps)
    ledger, indexed, works = _ledger(project, bindings)
    rounds = _rounds(request, questions, ledger, indexed, works)
    proposals = []
    for proposal in _array(request.get("proposed_queries", []), "proposed queries", 40):
        _keys(proposal, {"question_id", "dimension", "query", "reason", "gap_id"}, "proposed query")
        if not isinstance(proposal.get("question_id"), str):
            raise ValueError("proposed query needs an existing question ID")
        question = questions.get(proposal.get("question_id"))
        if question is None or proposal.get("dimension") not in {*question["dimensions"], "counterevidence", "question_gap"}:
            raise ValueError("proposed query needs a selected question/dimension")
        if proposal.get("gap_id") and proposal["gap_id"] not in {g["gap_id"] for g in question["gaps"]}:
            raise ValueError("proposed query references an unknown coverage gap")
        wb._text(proposal.get("query"), "proposed query", 2000)
        wb._text(proposal.get("reason"), "proposed query reason")
        matches = [row["receipt_id"] for row in ledger if row.get("query") == proposal["query"]]
        proposals.append({**proposal, "existing_attempt_ids": matches, "executed": False,
                          "status": "proposal_only_reuse_prior_receipts_before_search"})
    relations, seen = [], set()
    for relation in _array(request.get("relations", []), "notebook relations", 100):
        _keys(relation, {"id", "kind", "from", "to", "reason", "applicability"}, "notebook relation")
        identifier = wb._id(relation.get("id"), "relation ID")
        if identifier in seen or relation.get("kind") not in {"complements", "contradicts", "supersedes"}:
            raise ValueError("relations need distinct IDs and a supported declarative kind")
        seen.add(identifier)
        wb._text(relation.get("reason"), "relation reason")
        wb._text(relation.get("applicability"), "relation applicability")
        left, right = _reference(relation.get("from"), questions), _reference(relation.get("to"), questions)
        if left == right:
            raise ValueError("a notebook relation needs two different existing records")
        relations.append({**relation, "from": left, "to": right,
            "status": "declared_pending_semantic_review", "originals_retained": True,
            "automatic_truth_or_supersession": False})
    maximum = request.get("max_actions", 20)
    if type(maximum) is not int or not 1 <= maximum <= 40:
        raise ValueError("max_actions must be 1..40")
    modules = {p.name: sha(p) for p in (Path(__file__), Path(notebook.__file__), Path(reading.__file__),
        Path(reasoning.__file__), Path(intelligence.__file__), Path(wb.__file__),
        Path(__file__).with_name("research_artifacts.py"), Path(__file__).with_name("literature_evidence.py"),
        Path(__file__).with_name("output_provenance.py"))}
    return {"schema_version": "1.0", "kind": "research_frontier", "id": identity,
        "request_binding": {"path": request_file, "sha256": sha(request_path)},
        "input_bindings": sorted(bindings, key=lambda row: row["path"]), "module_hashes": modules,
        "questions": list(questions.values()), "query_rounds": rounds, "max_actions": maximum,
        "worklist": worklist[:maximum], "deferred_action_count": max(0, len(worklist) - maximum),
        "proposed_queries": proposals, "relations": relations,
        "attempt_summary": [{"receipt_id": r["receipt_id"], "status": r["status"],
            "query": r.get("query"), "error": r.get("error")} for r in ledger],
        "paid_calls": 0, "network_calls": 0, "scientific_saturation_verified": False,
        "scientific_completion_verified": False, "semantic_support_verified": False,
        "gate_approved": False, "originals_retained": True}


def _envelope(payload):
    digest = _digest(payload)
    return {**payload, "report_sha256": digest,
            "report_path": f"{OUTPUT}/{payload['id']}-{digest}.json"}


def refresh(project: Path, request_file: str = DEFAULT) -> dict:
    from scripts.literaturectl import require_cloud
    require_cloud()
    project = Path(project).resolve()
    report = _envelope(_prepare(project, request_file))
    target = path_in(project, report["report_path"], exists=False)
    changed = not target.exists()
    if changed:
        write(target, report)
        record(project, [target], MODULE)
    else:
        _origin(project, target, MODULE)
        if read(target) != report:
            raise ValueError("immutable frontier report changed; retain originals")
    return {**report, "changed": changed}


def model_context(project: Path, report_relative: str, role: str) -> dict:
    """Fully validate, then project a bounded summary without copying evidence."""
    if role not in {"writer", "planner", "critic", "remediator"}:
        raise ValueError("unsupported frontier model role")
    project = Path(project).resolve()
    if not isinstance(report_relative, str) or not re.fullmatch(re.escape(OUTPUT) + r"/[A-Za-z0-9][A-Za-z0-9_-]{0,79}-[a-f0-9]{64}\.json", report_relative):
        raise ValueError("frontier context must select one immutable report")
    target = path_in(project, report_relative)
    _origin(project, target, MODULE)
    report = read(target)
    expected = _envelope(_prepare(project, report.get("request_binding", {}).get("path", "")))
    if report != expected or report_relative != expected["report_path"]:
        raise ValueError("frontier report is stale or changed; refresh from current sources")
    return _context_projection(report, role)


def _context_text(row, source, fields):
    # Omit long text whole and preserve its durable record locator. Original
    # evidence is never shortened or edited to meet a prompt budget.
    for field in fields:
        value = source.get(field)
        if isinstance(value, str):
            if len(value) <= 240:
                row[field] = value
            else:
                row[field + "_omitted_characters"] = len(value)
    return row


def _context_projection(report, role):
    facts, questions, sources, source_ids = [], [], [], set()
    total_facts = unknown = contrary = 0
    evidence_count = decision_count = 0
    for qi, question in enumerate(report["questions"]):
        notebook_record = question["notebook"]
        evidence_count += len(notebook_record["evidence"])
        decision_count += len(notebook_record["decisions"])
        current_unknown = sum(not d.get("reusable_evidence") and d["dimension"] != "metadata"
            for p in question["coverage"] for d in p["dimensions"])
        unknown += current_unknown
        contrary += len(question["contrary_evidence_ids"])
        questions.append(_context_text({"question_id": question["question_id"],
            "paper_ids": question["paper_ids"][:5], "paper_count": len(question["paper_ids"]),
            "paper_ids_omitted": max(0, len(question["paper_ids"]) - 5),
            "dimensions": question["dimensions"], "unknown_dimension_count": current_unknown,
            "contrary_evidence_count": len(question["contrary_evidence_ids"]),
            "locator": f"#/questions/{qi}"}, question, ("question",)))
        for pi, paper in enumerate(question["coverage"]):
            if paper["paper_id"] not in source_ids:
                source_ids.add(paper["paper_id"])
                if len(sources) < 10:
                    sources.append({"paper_id": paper["paper_id"], "path": paper["source"]["path"],
                        "sha256": paper["source"]["sha256"],
                        "locator": f"#/questions/{qi}/coverage/{pi}/source"})
            for di, dimension in enumerate(paper["dimensions"]):
                total_facts += 1
                if len(facts) < 40:
                    answers = dimension.get("reusable_evidence", [])
                    facts.append({"question_id": question["question_id"], "paper_id": paper["paper_id"],
                        "dimension": dimension["dimension"], "status": dimension["status"],
                        "location_count": len(dimension["locations"]), "attributed_answer_count": len(answers),
                        "contrary_answer_count": sum(e.get("outcome") == "contradicts" for e in answers),
                        "semantic_support_verified": False,
                        "locator": f"#/questions/{qi}/coverage/{pi}/dimensions/{di}"})
    rounds = []
    for index, original in enumerate(report["query_rounds"][:20]):
        keys = ("id", "question_id", "dimension", "normalized_observation_count", "canonical_paper_count",
                "new_paper_count", "failed_attempt_count", "successful_attempt_count",
                "new_attributed_evidence_dimension_count", "evidence_round_association")
        row = {key: original[key] for key in keys}
        row.update(receipt_count=len(original["receipt_ids"]), receipt_ids=original["receipt_ids"][:3],
            receipt_ids_omitted=max(0, len(original["receipt_ids"]) - 3),
            reused_receipt_count=len(original["reused_receipt_ids"]),
            new_canonical_ids=original["new_canonical_ids"][:3],
            new_canonical_ids_omitted=max(0, len(original["new_canonical_ids"]) - 3),
            locator=f"#/query_rounds/{index}")
        if role != "critic":
            row["advice"] = original["advice"]
        rounds.append(row)
    context = {"kind": "research_frontier_factual_context" if role == "critic" else "research_frontier_action_context",
        "report_path": report["report_path"], "report_sha256": report["report_sha256"],
        "locator_basis": "JSON pointers resolve within this immutable report; scientific sources load separately.",
        "limits": {"coverage_observations": 40, "query_rounds": 20, "source_bindings": 10,
                   "action_rows_per_kind": report["max_actions"]},
        "counts": {"questions": len(report["questions"]), "coverage_observations": total_facts,
            "unknown_dimensions": unknown, "contrary_notebook_observations": contrary,
            "notebook_evidence_records": evidence_count, "notebook_decision_records": decision_count,
            "query_rounds": len(report["query_rounds"]), "source_bindings": len(source_ids),
            "input_bindings": len(report["input_bindings"]), "actual_attempts": len(report["attempt_summary"]),
            "failed_attempts": sum(r["status"] == "failed" for r in report["attempt_summary"])},
        "questions": questions, "coverage_observations": facts, "query_rounds": rounds, "source_bindings": sources,
        "omitted_counts": {"coverage_observations": total_facts - len(facts),
            "query_rounds": len(report["query_rounds"]) - len(rounds), "source_bindings": len(source_ids) - len(sources),
            "input_binding_rows": len(report["input_bindings"]), "attempt_rows": len(report["attempt_summary"]),
            "notebook_evidence_rows": evidence_count, "notebook_decision_rows": decision_count},
        "detail_locators": {"all_inputs": "#/input_bindings", "all_attempts": "#/attempt_summary",
            "all_questions_and_original_evidence": "#/questions", "all_rounds": "#/query_rounds"},
        "original_evidence_copied": False, "all_sources_read": False,
        "scientific_saturation_verified": False, "semantic_support_verified": False, "gate_approved": False}
    if role == "critic":
        return context
    action_keys = {
        "worklist": ("gap_id", "kind", "question_id", "paper_id", "dimension", "evidence_id", "reuse_source_id"),
        "proposed_queries": ("question_id", "dimension", "gap_id", "executed", "status"),
        "relations": ("id", "kind", "from", "to", "status", "originals_retained", "automatic_truth_or_supersession")}
    for field, keys in action_keys.items():
        rows = []
        for index, original in enumerate(report[field][:report["max_actions"]]):
            row = {key: original[key] for key in keys if key in original}
            row["locator"] = f"#/{field}/{index}"
            if "hypothesis_ids" in original:
                row["hypothesis_ids"] = original["hypothesis_ids"][:3]
                row["hypothesis_ids_omitted"] = max(0, len(original["hypothesis_ids"]) - 3)
            if field == "relations":
                # Endpoints need existing IDs, not the complete source-evidence list.
                for endpoint in ("from", "to"):
                    row[endpoint] = {key: original[endpoint][key] for key in ("question_id", "kind", "id")}
            _context_text(row, original, ("query", "reason", "applicability"))
            rows.append(row)
        context[field] = rows
        context["omitted_counts"][field + "_rows"] = len(report[field]) - len(rows)
        context["detail_locators"][field] = "#/" + field
    context["deferred_action_count"] = report["deferred_action_count"]
    return context
