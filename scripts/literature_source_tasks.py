"""Source-tracing dossiers and advisory screening over existing evidence.

No model calls, acquisition or human decisions. A matched metadata record,
located quote and semantic support are deliberately separate states.
"""
from __future__ import annotations

import html
from pathlib import Path
import re

from scripts import literature_workbench as wb, systematic_review
from scripts.research_artifacts import path_in, record, sha, write, matches_origin

OUTPUT = "reports/literature-source-tasks"
OPERATIONS = {"source_trace", "screening_advice"}
JUDGMENTS = {"claim_evidence": ("claim_evidence", "build"), "citation_crosscheck": ("citation_audit", "crosscheck"),
    "novelty_adjudication": ("innovation_screening", "adjudication"),
    "judgment_benchmark": ("literature_benchmark", "judgment_benchmark"), "research_memory": ("research_notebook", "failed_memory")}
OPERATIONS |= set(JUDGMENTS)
CONTROL = "program/research-control.json"
RESPONSE_FIELDS = {"claim_evidence", "novelty_adjudication", "citation_extraction", "anchor_labels"}


def validate_response_fields(value: dict) -> None:
    """Keep optional scientific results in the existing protected response."""
    for field in RESPONSE_FIELDS & value.keys():
        rows = value[field]
        if field == "citation_extraction":
            if not isinstance(rows, dict) or set(rows) != {"source", "records"}:
                raise ValueError("citation_extraction needs its source and records")
            rows = rows["records"]
        if not isinstance(rows, list) or len(rows) > 5000 or any(not isinstance(row, dict) for row in rows):
            raise ValueError(field + " needs bounded structured scientific results")


def _selections(project):
    target = path_in(project, CONTROL, exists=False)
    if not target.exists():
        return []
    value = wb._json(target.read_bytes())
    selected = value.get("scientific_judgments", [])
    if not isinstance(selected, list) or len(selected) > 20:
        raise ValueError("select at most twenty existing scientific judgment tasks")
    from scripts.review_receipts import STAGES
    for row in selected:
        _keys(row, {"operation", "request_file", "stages", "paper_id", "panel_views"}, "scientific judgment selection")
        if row.get("operation") not in JUDGMENTS or not isinstance(row.get("request_file"), str) or not row["request_file"].startswith("program/"):
            raise ValueError("scientific judgment selection needs its operation and program request")
        stages = row.get("stages")
        if not isinstance(stages, list) or not stages or any(stage not in STAGES.values() for stage in stages):
            raise ValueError("scientific judgment selection needs explicit actual stages")
        if "paper_id" in row and not re.fullmatch(r"P[0-9]{2}", str(row["paper_id"])):
            raise ValueError("scientific judgment paper must be Pxx")
        seats = row.get("panel_views", [])
        if not isinstance(seats, list) or any(seat not in {"domain", "editorial", "statistics"} for seat in seats):
            raise ValueError("select explicit existing panel views")
    return selected


def excluded_context_paths(project: Path) -> set[str]:
    """Answer keys are bound for freshness but never delivered to reviewers."""
    hidden = {CONTROL}
    for row in _selections(project):
        request = path_in(project, row["request_file"])
        spec = wb._json(request.read_bytes())
        hidden.add(row["request_file"])
        sample = spec.get("sample_labels")
        if isinstance(sample, str): hidden.add(sample)
        elif isinstance(sample, dict): hidden.add(sample["path"])
        for binding in spec.get("extractions", []) + spec.get("predictions", []):
            hidden.add(binding["path"])
        if row["operation"] == "judgment_benchmark":
            binding = spec["anchor_set"]
            hidden.add(binding["path"])
            anchors = wb._json(path_in(project, binding["path"]).read_bytes())
            for case in anchors.get("cases", []):
                hidden.update(case[key]["path"] for key in ("review", "rights") if key in case)
    return hidden


def selected_context(project: Path, stage: str, paper_id: str | None = None, *, seat: str | None = None) -> dict:
    """Add selected source tasks to an existing invocation; never call a model."""
    packets, dependencies, seen = [], {}, set()
    for row in _selections(project):
        if stage not in row["stages"] or (paper_id is not None and row.get("paper_id") and row["paper_id"] != paper_id):
            continue
        if seat is not None and seat not in row.get("panel_views", ["domain"] if row["operation"] == "claim_evidence" else []):
            continue
        operation = row["operation"]
        if operation in seen:
            raise ValueError("one task per judgment operation is allowed in an invocation")
        seen.add(operation)
        prepared = prepare_panel_task(project, operation, row["request_file"], paper_id=paper_id)
        if paper_id is not None and prepared["packet"].get("paper_id") not in {None, paper_id}:
            raise ValueError("selected scientific task belongs to another paper")
        packets.append({"operation": operation, "request_file": row["request_file"], "packet": prepared["packet"]})
        dependencies.update((source["path"], source["sha256"]) for source in prepared["sources"])
    if packets: dependencies[CONTROL] = sha(path_in(project, CONTROL))
    return {"tasks": packets, "sources": [{"path": path, "sha256": digest} for path, digest in sorted(dependencies.items())],
        "hidden_paths": sorted(excluded_context_paths(project))}


def integrity_errors(project: Path, paper_id: str, *, require_support=False) -> list[str]:
    """Keep drafts provisional; final submission needs actual current source review."""
    errors = []
    expected_citations, covered_citations, expected_usages, covered_usages = set(), set(), {}, set()
    if require_support:
        try:
            from scripts.claim_evidence import manuscript_usages
            expected_usages = {row["usage_id"]: row for row in manuscript_usages(project, paper_id)}
            expected_citations = {row["citation_key"] for row in expected_usages.values()}
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append("full-text citation coverage cannot be checked: " + str(exc))
    try:
        selected = _selections(project)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return ["scientific judgment selection: " + str(exc)]
    for task in selected:
        operation = task["operation"]
        if (operation not in {"claim_evidence", "citation_crosscheck"} or "writing-and-review" not in task["stages"]
                or task.get("paper_id", paper_id) != paper_id):
            continue
        try:
            spec = wb._json(path_in(project, task["request_file"]).read_bytes())
            if spec.get("paper_id", paper_id) != paper_id:
                if "paper_id" in task:
                    raise ValueError("selected request belongs to a different paper")
                continue
            report = build(project, operation, spec)
            if operation == "claim_evidence":
                for claim in report["claims"]:
                    covered_citations.add(claim["citation_key"])
                    covered_usages.update(row["usage_id"] for row in claim["manuscript_usages"])
                    if any(row["outcome"] == "contradicts" for row in claim["judgments"]):
                        errors.append("source-bound citation contradiction remains unresolved: " + claim["claim_id"])
                    elif require_support and (not claim["full_text_ready"] or not claim["judgments"] or claim["outcome"] != "supports"):
                        errors.append("full-text citation support remains unverified or insufficient: " + claim["claim_id"])
            elif report["differences"]:
                errors.append("independent citation extraction has unresolved bibliographic differences: " + spec["id"])
        except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            errors.append("scientific judgment " + operation + ": " + str(exc))
    if expected_citations - covered_citations:
        errors.append("final submission needs a current full-text claim_evidence task covering cited keys: "
            + ", ".join(sorted(expected_citations - covered_citations)))
    for identifier in sorted(expected_usages.keys() - covered_usages):
        row = expected_usages[identifier]
        errors.append("final submission has an uncovered citation use: " + row["citation_key"] + " at "
            + row["source"]["path"] + ":" + str(row["source"].get("line", row["source"].get("paragraph"))))
    return errors


def _implementation(operation):
    if operation not in JUDGMENTS:
        return sha(Path(__file__))
    return wb._digest({name: sha(Path(__file__).with_name(name + ".py"))
        for name in ("literature_source_tasks", JUDGMENTS[operation][0])})


def judgment_responses(project: Path, paper_id: str | None = None) -> list[dict]:
    """Current protected stage observations plus an already-run final panel.

    Absence is a preparation state. Existing but broken/stale records are errors;
    they cannot be erased or silently replaced by an empty assessment.
    """
    from scripts import review_receipts
    from scripts.research_artifacts import read
    state_path = path_in(project, "state/run.json", exists=False)
    state = read(state_path) if state_path.is_file() else {}
    stage = state.get("stage")
    if paper_id and stage in {None, "writing-and-review", "submission-ready"}:
        from scripts import review_panel
        directory = path_in(project, f"{review_panel.PREFIX}/{paper_id}", exists=False)
        pointer = directory / "latest.json"
        if pointer.exists() or pointer.is_symlink():
            return review_panel.responses(project, paper_id)
        if directory.exists() and any(directory.rglob("*.json")):
            raise ValueError("scientific judgment panel history exists but its latest pointer is missing")
    result = []
    if stage in review_receipts.STAGES.values():
        gate = next(g for g, name in review_receipts.STAGES.items() if name == stage)
        from scripts.paper_execution import enabled, selected
        paper = selected(project, paper_id) if enabled(project) and gate in {"G3", "G4", "G5"} else paper_id if gate == "G5" else None
        directory = path_in(project, f"{review_receipts.PREFIX}/{review_receipts._key(gate, paper)}", exists=False)
        pointer = directory / "observation-latest.json"
        if pointer.exists() or pointer.is_symlink():
            receipt = review_receipts.observation(project, stage, paper)["receipt"]
            if receipt["materials"] != review_receipts.material_snapshot(project, stage, paper):
                raise ValueError("scientific judgment observation is stale for its current task/source inputs")
            result.append({"receipt": {**receipt, "response": receipt["audit"], "role": "independent-critic-observation"},
                "response": read(path_in(project, receipt["audit"]["path"]))})
        elif directory.exists() and any(directory.glob("*/observation.json")):
            raise ValueError("scientific judgment observation history exists but its latest pointer is missing")
    return result


def _keys(value, allowed, label):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(label + " has unsupported fields")


def _text(value, label, limit=4000):
    return wb._text(value, label, limit)


def _bound(project, value, *, prefixes=("evidence/", "reports/", "program/")):
    _keys(value, {"path", "sha256"}, "binding")
    relative = value.get("path")
    if not isinstance(relative, str) or not relative.startswith(prefixes):
        raise ValueError("evidence binding needs an allowed project-relative file")
    target = wb._path(project, relative)
    if target.stat().st_size > 4_000_000 or sha(target) != value.get("sha256"):
        raise ValueError("bound evidence changed or exceeds 4 MB")
    return {"path": relative, "sha256": value["sha256"]}


def _library(project):
    library, _, manifest = wb._snapshot(project)
    return {p["id"]: p for p in library["papers"] if p.get("status") == "current"}, manifest


def _anchors(project, paper, incoming):
    if not isinstance(incoming, list) or len(incoming) > 20:
        raise ValueError("evidence requires at most twenty original-source anchors")
    result = []
    original = {paper["source"]["path"], (paper.get("reader") or {}).get("path")}
    for anchor in incoming:
        if not isinstance(anchor, dict) or anchor.get("path") not in original:
            raise ValueError("evidence must quote the original source or its controlled reader")
        result.append(wb.validate_anchor(project, paper, anchor))
    return result


def _receipt(project, receipt_id):
    _text(receipt_id, "receipt ID", 120)
    path = path_in(project, "evidence/literature-api-ledger.jsonl")
    rows = [r for r in systematic_review._read_jsonl(path) if r.get("receipt_id") == receipt_id]
    if len(rows) != 1 or rows[0].get("status") != "success":
        raise ValueError("an actual unique successful search receipt is required")
    receipt = rows[0]
    from scripts.literature_intelligence import _receipt_works
    _receipt_works(project, receipt)
    target = wb._path(project, receipt["normalized_results_path"])
    return receipt, {"path": target.relative_to(project).as_posix(), "sha256": sha(target)}


def _full_text_available(project, paper):
    if not paper:
        return False
    reader = paper.get("reader")
    if reader:
        receipt = wb._json(wb._path(project, reader["receipt"]["path"]).read_bytes())
        count = receipt.get("page_count")
        return (type(count) is int and count > 0 and receipt.get("selected_pages") == list(range(1, count + 1))
                and {int(page) for page in reader["page_ranges"]} == set(range(1, count + 1)))
    from scripts import source_scope
    relative = "evidence/source-scopes/" + paper["source"]["sha256"] + ".json"
    target = path_in(project, relative, exists=False)
    return target.is_file() and not source_scope.verify(project, paper["source"],
        {"path": relative, "sha256": sha(target)}, "full_text")


def source_trace(project: Path, spec: dict) -> dict:
    _keys(spec, {"schema_version", "id", "memory_statement", "search_leads", "candidates"}, "source trace")
    if spec.get("schema_version") != "1.0":
        raise ValueError("unsupported source trace schema")
    identifier = wb._id(spec.get("id"), "source trace ID")
    memory = _text(spec.get("memory_statement"), "remembered statement")
    papers, manifest = _library(project)
    incoming = spec.get("candidates")
    if not isinstance(incoming, list) or not 1 <= len(incoming) <= 100:
        raise ValueError("source trace needs 1..100 registered candidate papers")
    ids = [c.get("paper_id") for c in incoming if isinstance(c, dict)]
    if len(ids) != len(incoming) or any(not isinstance(p, str) or p not in papers for p in ids) or len(set(ids)) != len(ids):
        raise ValueError("trace candidates must be distinct current registered papers")
    leads, bindings = [], []
    searches = spec.get("search_leads", [])
    if not isinstance(searches, list) or len(searches) > 50:
        raise ValueError("at most fifty explicit retrieval leads")
    for lead in searches:
        _keys(lead, {"query", "provider", "status", "receipt_id"}, "search lead")
        query = _text(lead.get("query"), "search query", 1000)
        provider = _text(lead.get("provider"), "search provider", 100)
        status = lead.get("status")
        if status not in {"planned", "executed"}:
            raise ValueError("search lead status must be planned or executed")
        if status == "executed":
            receipt, binding = _receipt(project, lead.get("receipt_id"))
            if receipt.get("mode") != "live_search":
                raise ValueError("an imported metadata receipt cannot establish an executed platform search")
            if receipt.get("query") != query or receipt.get("provider") != provider:
                raise ValueError("search lead differs from its actual query/provider receipt")
            bindings.append(binding)
        elif "receipt_id" in lead:
            raise ValueError("a planned search cannot masquerade as executed evidence")
        leads.append(dict(lead))
    candidates = []
    for candidate in incoming:
        _keys(candidate, {"paper_id", "state", "reason", "evidence", "premises", "scope", "inference_boundary",
                          "identity_evidence", "cites_candidate_ids"}, "trace candidate")
        paper = papers[candidate["paper_id"]]
        state = candidate.get("state", "candidate")
        if state not in {"candidate", "excluded"}:
            raise ValueError("candidate state is not a verification verdict")
        reason = _text(candidate.get("reason"), "candidate inclusion/exclusion reason")
        boundary = _text(candidate.get("inference_boundary"), "candidate inference boundary")
        evidence = _anchors(project, paper, candidate.get("evidence", []))
        premises = []
        for field in ("premises", "scope"):
            rows = candidate.get(field, [])
            if not isinstance(rows, list) or len(rows) > 20:
                raise ValueError("premises and scope must contain bounded source-bound statements")
            checked = []
            for item in rows:
                _keys(item, {"text", "evidence"}, field)
                anchors = _anchors(project, paper, item.get("evidence", []))
                if not anchors:
                    raise ValueError("premise/scope statements require original evidence")
                checked.append({"text": _text(item.get("text"), field), "evidence": anchors,
                                "semantic_support_verified": False})
            premises.append(checked)
        cites = candidate.get("cites_candidate_ids", [])
        if (not isinstance(cites, list) or any(not isinstance(p, str) for p in cites) or len(set(cites)) != len(cites)
                or any(p not in ids or p == paper["id"] for p in cites) or cites and not evidence):
            raise ValueError("citation-chain leads need distinct other candidates and located original evidence")
        identity = {"state": "metadata_not_checked", "title": paper["title"], "year": None,
                    "doi": None, "authors": None, "original_pdf_identity_verified": False}
        supplied = candidate.get("identity_evidence")
        if supplied is not None:
            _keys(supplied, {"receipt_id", "study_id"}, "identity evidence")
            receipt, binding = _receipt(project, supplied.get("receipt_id"))
            works, _ = systematic_review.verified_works(project, [supplied["receipt_id"]])
            matches = [w for w in works if w["study_id"] == supplied.get("study_id")]
            if len(matches) != 1:
                raise ValueError("identity must point to an actual normalized metadata work")
            work = matches[0]["work"]
            normalize = lambda text: " ".join(str(text).casefold().split())
            if normalize(work.get("title")) != normalize(paper["title"]):
                raise ValueError("candidate title differs from its metadata identity evidence")
            identity.update(state="metadata_title_matched", receipt_id=receipt["receipt_id"],
                study_id=matches[0]["study_id"], title=work.get("title"), year=work.get("publication_year"), doi=work.get("doi"),
                authors=work.get("authors"))
            bindings.append(binding)
        candidates.append({"paper_id": paper["id"], "title": paper["title"], "source": paper["source"],
            "source_scope": paper.get("source_scope"), "candidate_state": state, "reason": reason,
            "identity": identity, "text_state": "original_passages_located" if evidence else "not_located",
            "semantic_state": "pending_source_review", "evidence": evidence, "premises": premises[0],
            "scope": premises[1], "inference_boundary": boundary, "cites_candidate_ids": cites,
            "citation_chain_verified": False, "earliest_original_source_established": False})
    return {"schema_version": "1.0", "operation": "source_trace", "id": identifier,
        "memory_statement": memory, "search_leads": leads, "candidates": candidates,
        "metadata_bindings": bindings, "workbench_manifest_sha256": sha(project / manifest["output_dir"] / "manifest.json"),
        "semantic_support_verified": False, "earliest_original_source_established": False,
        "model_call_made": False, "scientific_completion_verified": False}


def screening_advice(project: Path, spec: dict) -> dict:
    _keys(spec, {"schema_version", "id", "screening", "criteria", "study_papers", "advice", "duplicate_leads"}, "screening advice")
    if spec.get("schema_version") != "1.0":
        raise ValueError("unsupported screening advice schema")
    identifier = wb._id(spec.get("id"), "screening advice ID")
    binding = _bound(project, spec.get("screening"), prefixes=("evidence/systematic/",))
    ledger = wb._json(path_in(project, binding["path"]).read_bytes())
    for receipt_id in ledger.get("receipt_ids", []):
        _receipt(project, receipt_id)
    assessed = systematic_review.assess(project, path_in(project, binding["path"]))
    studies = {s["study_id"]: s for s in ledger["studies"]}
    if len(studies) > 200:
        raise ValueError("screening advice is bounded to two hundred current studies")
    protocol = ledger.get("protocol")
    protocol_binding = _bound(project, {k: protocol[k] for k in ("path", "sha256")}) if protocol else None
    criteria = spec.get("criteria")
    if not isinstance(criteria, list) or not 1 <= len(criteria) <= 20:
        raise ValueError("screening advice requires 1..20 exact existing criteria")
    criterion_ids, criterion_texts, intervals = set(), set(), []
    formal_criteria = ledger.get("criteria", "")
    for criterion in criteria:
        _keys(criterion, {"id", "text"}, "criterion")
        key = wb._id(criterion.get("id"), "criterion ID")
        text = _text(criterion.get("text"), "criterion text")
        matches = list(re.finditer(re.escape(text), formal_criteria))
        if key in criterion_ids or text.strip().casefold() in criterion_texts or len(matches) != 1:
            raise ValueError("criterion text must quote the frozen screening criteria exactly")
        criterion_ids.add(key)
        criterion_texts.add(text.strip().casefold())
        intervals.append((matches[0].start(), matches[0].end()))
    cursor, remainder = 0, []
    for first, last in sorted(intervals):
        if first < cursor:
            raise ValueError("criterion mappings overlap or repeat formal rule text")
        remainder.append(formal_criteria[cursor:first])
        cursor = last
    remainder.append(formal_criteria[cursor:])
    if re.sub(r"[\s;]+", "", "".join(remainder)):
        raise ValueError("criterion mappings must cover the complete frozen screening criteria; use the whole rule as one criterion when needed")
    papers, manifest = _library(project)
    mappings = spec.get("study_papers", [])
    if not isinstance(mappings, list) or len(mappings) > len(studies):
        raise ValueError("study-to-paper mapping must be bounded to existing studies")
    mapped = {}
    for item in mappings:
        _keys(item, {"study_id", "paper_id"}, "study mapping")
        if item.get("study_id") not in studies or item.get("paper_id") not in papers or item["study_id"] in mapped:
            raise ValueError("study mapping needs a unique existing study and current paper")
        paper = papers[item["paper_id"]]
        title = " ".join(str(studies[item["study_id"]]["work"].get("title", "")).casefold().split())
        if title != " ".join(paper["title"].casefold().split()):
            raise ValueError("screening study and workbench paper titles differ")
        mapped[item["study_id"]] = paper
    incoming = spec.get("advice", [])
    if not isinstance(incoming, list) or len(incoming) > len(studies) * len(criteria) * 2:
        raise ValueError("screening advice must be bounded to declared studies, stages and criteria")
    selected = {}
    for item in incoming:
        _keys(item, {"study_id", "stage", "criterion_id", "suggestion", "reason", "missing_information", "evidence"}, "advisory item")
        key = (item.get("study_id"), item.get("stage"), item.get("criterion_id"))
        if (key[0] not in studies or key[1] not in {"title_abstract", "full_text"}
                or key[2] not in criterion_ids or key in selected):
            raise ValueError("duplicate or out-of-scope screening advice")
        suggestion = item.get("suggestion")
        if suggestion not in {"include", "exclude", "review"}:
            raise ValueError("AI advice is include/exclude/review, never a formal decision")
        missing = item.get("missing_information", [])
        if not isinstance(missing, list) or len(missing) > 20 or any(not isinstance(v, str) or not v.strip() for v in missing):
            raise ValueError("missing information must be explicit bounded reasons")
        paper = mapped.get(key[0])
        if item.get("evidence") and paper is None:
            raise ValueError("advisory evidence requires a current registered paper mapping")
        evidence = _anchors(project, paper, item.get("evidence", [])) if paper else []
        if suggestion != "review" and not evidence:
            raise ValueError("include/exclude suggestions need original criterion evidence")
        full_scope = _full_text_available(project, paper)
        if key[1] == "full_text" and (not full_scope or not evidence):
            if suggestion != "review":
                raise ValueError("unavailable full text requires review, never exclusion or inclusion")
            missing = [*missing, "Original full-text criterion evidence is not available."]
        selected[key] = {"study_id": key[0], "stage": key[1], "criterion_id": key[2],
            "suggestion": suggestion, "reason": _text(item.get("reason"), "advice reason"),
            "missing_information": missing, "evidence": evidence, "semantic_support_verified": False}
    rows = []
    for study_id, study in studies.items():
        for stage in ("title_abstract", "full_text"):
            for criterion in criteria:
                key = (study_id, stage, criterion["id"])
                row = selected.get(key, {"study_id": study_id, "stage": stage, "criterion_id": criterion["id"],
                    "suggestion": "review", "reason": "No source-bound advice supplied for this criterion.",
                    "missing_information": ["Locate actual criterion evidence."], "evidence": [],
                    "semantic_support_verified": False})
                rows.append({**row, "formal_decision_snapshot": study[stage]["decision"], "formal_decision_modified": False})
    duplicates = spec.get("duplicate_leads", [])
    if not isinstance(duplicates, list) or len(duplicates) > 200:
        raise ValueError("at most two hundred explicit duplicate-study leads")
    checked_duplicates = []
    for item in duplicates:
        _keys(item, {"study_ids", "reason"}, "duplicate lead")
        ids = item.get("study_ids")
        if (not isinstance(ids, list) or not 2 <= len(ids) <= 10 or any(not isinstance(i, str) for i in ids)
                or len(set(ids)) != len(ids) or any(i not in studies for i in ids)):
            raise ValueError("duplicate lead must identify distinct existing studies")
        checked_duplicates.append({"study_ids": ids, "reason": _text(item.get("reason"), "duplicate lead reason"),
                                   "metadata_basis": [{"study_id": i, "work": studies[i]["work"]} for i in ids],
                                   "same_study_verified": False, "records_merged": False})
    return {"schema_version": "1.0", "operation": "screening_advice", "id": identifier,
        "screening": binding, "protocol": protocol_binding, "criteria": criteria,
        "criteria_sha256": wb._digest(ledger["criteria"]), "formal_criteria_text": ledger["criteria"],
        "criterion_text_coverage_complete": True, "criterion_mapping_is_scientifically_complete": False,
        "advice": rows, "duplicate_leads": checked_duplicates,
        "formal_counts_snapshot": assessed, "workbench_manifest_sha256": sha(project / manifest["output_dir"] / "manifest.json"),
        "formal_decisions_modified": False, "human_review_required": True, "model_call_made": False,
        "scientific_completion_verified": False}


def build(project: Path, operation: str, spec: dict) -> dict:
    if operation not in OPERATIONS:
        raise ValueError("unsupported source task operation")
    if operation in JUDGMENTS:
        from importlib import import_module
        module, function = JUDGMENTS[operation]
        return getattr(import_module("scripts." + module), function)(project, spec)
    return source_trace(project, spec) if operation == "source_trace" else screening_advice(project, spec)


def _paths(project, operation, identifier):
    directory = path_in(project, OUTPUT + "/" + operation + "/" + wb._id(identifier), exists=False)
    return directory, directory / "report.json", directory / "manifest.json"


def _existing(project, report, manifest):
    if not report.exists() and not manifest.exists():
        return None
    if not report.is_file() or not manifest.is_file():
        raise ValueError("source task output inventory is incomplete")
    record_value = wb._json(manifest.read_bytes())
    outputs = record_value.get("outputs")
    expected = {report.relative_to(project).as_posix(), report.with_name("index.html").relative_to(project).as_posix()}
    if not isinstance(outputs, list) or len(outputs) != 2 or {o.get("path") for o in outputs} != expected:
        raise ValueError("source task output inventory differs")
    for item in outputs:
        target = path_in(project, item["path"])
        if sha(target) != item["sha256"] or not matches_origin(project, target, model="scripts/literature_source_tasks.py"):
            raise ValueError("source task output changed outside its controlled builder")
    if not matches_origin(project, manifest, model="scripts/literature_source_tasks.py"):
        raise ValueError("source task manifest provenance is not current")
    history = record_value.get("history", [])
    if not isinstance(history, list):
        raise ValueError("source task history inventory is invalid")
    actual = {p.relative_to(project).as_posix() for p in report.parent.glob("history/*.json")}
    if len(history) != len(actual) or {h.get("path") for h in history} != actual:
        raise ValueError("source task history inventory changed or an archive was deleted")
    for item in history:
        target = path_in(project, item["path"])
        if sha(target) != item.get("sha256") or not matches_origin(project, target, model="scripts/literature_source_tasks.py"):
            raise ValueError("source task history archive changed")
    return wb._json(report.read_bytes())


def _html(report):
    import json
    return ('<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" '
            'content="default-src \'none\'; base-uri \'none\'; form-action \'none\'"><title>Source task</title>'
            '<h1>' + html.escape(report["operation"]) + '</h1><p>Advisory evidence; no scientific or human approval.</p><pre>' +
            html.escape(json.dumps(report, ensure_ascii=False, indent=2)) + '</pre>')


def refresh(project: Path, operation: str, request_path: str) -> dict:
    if not isinstance(request_path, str) or not request_path.startswith("program/") or Path(request_path).suffix != ".json":
        raise ValueError("source task request must be a JSON file under program/")
    source = wb._path(project, request_path)
    if source.stat().st_size > 2_000_000:
        raise ValueError("source task request exceeds 2 MB")
    spec = wb._json(source.read_bytes())
    report = build(project, operation, spec)
    directory, target, manifest_path = _paths(project, operation, report["id"])
    if directory.exists() and any(directory.iterdir()) and not manifest_path.is_file():
        raise ValueError("refusing to overwrite a directory owned by another tool")
    previous = _existing(project, target, manifest_path)
    if operation == "source_trace" and previous:
        before = {c["paper_id"] for c in previous["candidates"]}
        if not before <= {c["paper_id"] for c in report["candidates"]}:
            raise ValueError("retain earlier source candidates with exclusion reasons instead of deleting them")
    report["request"] = {"path": request_path, "sha256": sha(source)}
    report["implementation_sha256"] = _implementation(operation)
    view = directory / "index.html"
    history = []
    if previous is not None and previous != report:
        archive = directory / "history" / (wb._digest(previous) + ".json")
        write(archive, previous)
        history.append(archive)
    write(target, report)
    view.write_text(_html(report), encoding="utf-8")
    manifest = {"schema_version": "1.0", "operation": operation, "id": report["id"],
        "request": report["request"], "implementation_sha256": _implementation(operation),
        "outputs": [{"path": p.relative_to(project).as_posix(), "sha256": sha(p)} for p in (target, view)],
        "history": [{"path": p.relative_to(project).as_posix(), "sha256": sha(p)} for p in sorted(directory.glob("history/*.json"))]}
    write(manifest_path, manifest)
    record(project, [target, view, manifest_path, *history], "scripts/literature_source_tasks.py")
    return {"report": target.relative_to(project).as_posix(), "html": view.relative_to(project).as_posix(),
            "model_call_made": False, "operation": operation, "id": report["id"]}


def validate_saved_report(project: Path, operation: str, request_path: str) -> dict:
    source = wb._path(project, request_path)
    report = build(project, operation, wb._json(source.read_bytes()))
    _, target, manifest_path = _paths(project, operation, report["id"])
    previous = _existing(project, target, manifest_path)
    report["request"] = {"path": request_path, "sha256": sha(source)}
    report["implementation_sha256"] = _implementation(operation)
    manifest = wb._json(manifest_path.read_bytes())
    if previous != report or manifest.get("request") != report["request"] or manifest.get("implementation_sha256") != _implementation(operation):
        raise ValueError("source task input or implementation changed; rebuild the report")
    return {"valid": True, "semantic_support_verified": False, "human_decision": False}


def model_context(project: Path, operation: str, request_path: str, role: str) -> dict:
    """Explicit current-task context; critics never receive prior judgments/keys."""
    if role not in {"planner", "writer", "critic", "remediator"}:
        raise ValueError("unsupported scientific judgment role")
    validate_saved_report(project, operation, request_path)
    spec = wb._json(wb._path(project, request_path).read_bytes())
    if role == "critic" and operation in JUDGMENTS:
        return prepare_panel_task(project, operation, request_path)["packet"]
    _, target, _ = _paths(project, operation, spec["id"])
    report = wb._json(target.read_bytes())
    return report


def citation_source(project: Path, spec: dict, *, paper_id: str | None = None, dependencies: dict | None = None) -> dict:
    """Expose only a canonical paper source or a registered original/reader.

    A path/hash declaration alone grants no authority to send arbitrary project
    bytes to a critic. Hidden identities and hashes also survive file renames.
    """
    from scripts.research_artifacts import bound_source, read
    from scripts.output_provenance import current_origin
    if (not isinstance(spec, dict) or spec.get("schema_version") != "1.0"
            or set(spec) - {"schema_version", "id", "source", "extractions", "paper_id"}):
        raise ValueError("citation extraction requires the exact source request schema")
    binding = bound_source(project, spec["source"])
    relative, fingerprint = binding["path"], binding["sha256"]
    target = wb._path(project, relative)
    hidden = excluded_context_paths(project)
    for key in ("extractions", "predictions"):
        hidden.update(row["path"] for row in spec.get(key, []))
    state = path_in(project, "state/run.json", exists=False)
    expected = paper_id or spec.get("paper_id") or (read(state).get("active_paper") if state.is_file() else None)
    if paper_id and spec.get("paper_id") not in {None, paper_id}:
        raise ValueError("citation extraction belongs to another paper")
    hidden_hashes = set()
    for value in hidden:
        hidden_file = path_in(project, value, exists=False)
        if hidden_file.is_file(): hidden_hashes.add(sha(hidden_file))
    registry = path_in(project, "state/output-provenance.json", exists=False)
    if registry.is_file():
        for name, origin in read(registry).get("files", {}).items():
            if (name.startswith(("reviews/", "reports/", "state/", "program/"))
                    or any(word in str(origin.get("role", "")).casefold() for word in ("critic", "review", "extract", "judgment"))):
                hidden_hashes.add(origin.get("sha256"))
    if relative in hidden or fingerprint in hidden_hashes:
        raise ValueError("citation source is a hidden judgment, task/control record or renamed copy")
    origin = current_origin(project, target)
    if any(word in str(origin.get("role", "")).casefold() for word in ("critic", "review", "extract", "judgment")):
        raise ValueError("prior judgment/extraction cannot impersonate an original citation source")
    parts = Path(relative).parts
    if len(parts) >= 4 and parts[0] == "papers" and re.fullmatch(r"P[0-9]{2}", parts[1]):
        owner = parts[1]
        if expected is not None and owner != expected:
            raise ValueError("citation source must belong to the current panel paper")
        allowed = {f"papers/{owner}/manuscript/references.bib"}
        main = path_in(project, f"papers/{owner}/manuscript/main.tex", exists=False)
        if main.is_file():
            from scripts.citation_audit import tex_source_paths
            allowed.update(path.relative_to(project).as_posix() for path in tex_source_paths(main))
        if relative not in allowed:
            raise ValueError("citation source must be the actual canonical manuscript, TeX dependency or bibliography")
        from scripts.review_panel import _source
        _source(project, owner, relative)
        return binding
    # Registered full text and its controlled native reader carry acquisition,
    # rights, source-map and current-output checks; an arbitrary evidence/*.txt
    # or model-authored summary does not become an original by renaming it.
    from scripts.source_scope import _registered_basis
    papers, _ = _library(project)
    for paper in papers.values():
        candidates = [paper.get("source"), paper.get("reader")]
        if not any(isinstance(row, dict) and row.get("path") == relative and row.get("sha256") == fingerprint for row in candidates):
            continue
        primary, basis = _registered_basis(project, paper["id"])
        if primary != paper.get("source"):
            raise ValueError("citation original differs from its controlled registration")
        if dependencies is not None:
            dependencies[wb.CONFIG] = sha(path_in(project, wb.CONFIG))
            for prefix in ("registration", "acquisition", "manifest"):
                dependencies[basis[prefix + "_path"]] = basis[prefix + "_sha256"]
            dependencies[primary["path"]] = primary["sha256"]
        return binding
    raise ValueError("citation extraction requires a registered original source or controlled reader")


def prepare_panel_task(project: Path, operation: str, request_file: str, *, paper_id: str | None = None) -> dict:
    """Pure current inputs for selected existing seats; never read panel replies.

    Sources are fingerprint dependencies, not permission to expose their raw
    contents: benchmark answer keys and previous judgments stay out of packet.
    """
    if operation not in JUDGMENTS or not isinstance(request_file, str) or not request_file.startswith("program/"):
        raise ValueError("select one explicit scientific judgment task under program/")
    source = wb._path(project, request_file)
    if source.stat().st_size > 2_000_000:
        raise ValueError("scientific judgment request exceeds 2 MB")
    spec = wb._json(source.read_bytes())
    extra_sources = {}
    if operation == "claim_evidence":
        from scripts.claim_evidence import prepare
        packet = prepare(project, spec)
    elif operation == "novelty_adjudication":
        from scripts.innovation_screening import adjudication
        packet = adjudication(project, spec, observed=[])
        for pair in packet["pairs"]:
            for key in ("judgments", "decision", "merge_concern_present", "disagreement"):
                pair.pop(key, None)
    elif operation == "citation_crosscheck":
        from scripts.citation_audit import CROSSCHECK_ROLE_CONTRACT
        binding = citation_source(project, spec, paper_id=paper_id, dependencies=extra_sources)
        original = path_in(project, binding["path"])
        if original.stat().st_size > 150_000:
            raise ValueError("citation extraction source exceeds the prompt bound; select a smaller original source")
        packet = {"operation": operation, "id": spec["id"], "source": binding,
            "source_text": original.read_text(encoding="utf-8"), "role_contract": CROSSCHECK_ROLE_CONTRACT}
    elif operation == "judgment_benchmark":
        from scripts.literature_benchmark import judgment_benchmark
        report = judgment_benchmark(project, {k: v for k, v in spec.items() if k != "predictions"}, observed=[])
        packet = {"operation": operation, "id": spec["id"], "role_contract": report["role_contract"],
            "blind_cases": [{k: v for k, v in row.items() if k != "partition"} for row in report["blind_cases"]]}
    else:
        from scripts.research_notebook import failed_memory
        packet = failed_memory(project, spec)
    dependencies = {request_file: sha(source), **extra_sources}
    def collect(value):
        if isinstance(value, dict):
            if isinstance(value.get("path"), str) and "sha256" in value:
                path = path_in(project, value["path"])
                if sha(path) != value["sha256"]:
                    raise ValueError("scientific judgment input changed: " + value["path"])
                dependencies[value["path"]] = value["sha256"]
            for prefix in ("registration", "acquisition", "manifest"):
                if value.get(prefix + "_path"):
                    collect({"path": value[prefix + "_path"], "sha256": value[prefix + "_sha256"]})
            for item in value.values(): collect(item)
        elif isinstance(value, list):
            for item in value: collect(item)
    collect({k: v for k, v in spec.items() if k != "sample_labels"}); collect(packet)
    for key in ("anchor_set",):
        if key in spec:collect(wb._json(path_in(project, spec[key]["path"]).read_bytes()))
    if operation == "claim_evidence":
        from scripts.ref_verify_adapter import canonical_manuscript
        from scripts.citation_audit import tex_source_paths
        manuscript = canonical_manuscript(path_in(project, "papers/" + spec["paper_id"], exists=False))
        manuscripts = tex_source_paths(manuscript) if manuscript.suffix == ".tex" else {manuscript}
        for path in [*manuscripts, manuscript.parent / "references.bib"]:
            dependencies[path.relative_to(project).as_posix()] = sha(path)
    if operation in {"claim_evidence", "novelty_adjudication"}:
        for relative in ("program/literature-workbench.json", "program/originality-audit.json", "state/data-authorizations.json"):
            target = path_in(project, relative, exists=False)
            if target.is_file():dependencies[relative] = sha(target)
    return {"packet": packet, "sources": [{"path": p, "sha256": s} for p, s in sorted(dependencies.items())]}
