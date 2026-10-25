"""Evidence-bound method adoption, comparability, reading and review worklists."""
from __future__ import annotations

import re
from pathlib import Path
from scripts.research_artifacts import bound_source, path_in, read, record, sha, write

INPUT = "program/research-extensions.json"
OUTPUT = "reports/research-extensions/audit.json"
DIMENSIONS = ("population", "dataset_version", "split", "leakage", "metric_definition",
              "comparator", "tuning_budget", "assumptions", "independent_unit")
PERSPECTIVES = {"method", "statistics", "contribution"}
CLOSEST_AXES = ("research_object", "method", "result")
CLOSEST_CONTEXT = {
    "novelty_matrix": "program/novelty-claim-matrix.json",
    "originality_audit": "program/originality-audit.json",
    "literature_library": "program/literature-workbench.json",
}


def nonempty(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 12000:
        raise ValueError(f"{name} needs explicit bounded text")
    return value


def sources(project, rows):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 30:
        raise ValueError("one to thirty actual evidence anchors required")
    result = []
    for row in rows:
        bound = bound_source(project, row)
        target = path_in(project, bound["path"])
        if target.stat().st_size > 4_000_000:
            raise ValueError("use an authorized bounded text evidence extract")
        quote = nonempty(row.get("quote"), "source quote")
        if target.read_text(encoding="utf-8").count(quote) != 1:
            raise ValueError("source quote must occur exactly once in its current source")
        result.append({**bound, "quote": quote})
    return result


def _closest_own_anchor(project, anchor, paper_id):
    """Locate our protocol/result text, never our manuscript or audit verdict."""
    bound = bound_source(project, anchor)
    relative = bound["path"]
    parts = Path(relative).parts
    if (not relative.startswith(f"papers/{paper_id}/") or
            any(part.casefold() in {"state", "reports", "reviews", "api_runs", "submission",
                                    "manuscript", "manuscript-hygiene"} for part in parts) or
            Path(relative).suffix.lower() not in {".json", ".csv", ".txt", ".lean"}):
        raise ValueError("ours axis evidence must be this paper's protocol, result or proof; not its manuscript/review")
    target = path_in(project, relative)
    if target.stat().st_size > 4_000_000:
        raise ValueError("use a bounded own protocol/result extract")
    lines = target.read_text(encoding="utf-8").splitlines()
    first, last = anchor.get("start_line"), anchor.get("end_line")
    if type(first) is not int or type(last) is not int or not 1 <= first <= last <= len(lines):
        raise ValueError("ours axis anchor needs exact start_line/end_line")
    quote = nonempty(anchor.get("quote"), "axis source quote")
    if "\n".join(lines[first - 1:last]).count(quote) != 1:
        raise ValueError("axis quote must occur exactly once in the specified source lines")
    if anchor.get("pdf_page") is not None:
        raise ValueError("use a controlled literature reader for PDF page anchors")
    return {**bound, "quote": quote, "start_line": first, "end_line": last,
            "locator": f"lines {first}-{last}", "semantic_verification": False}


def _closest_prior_anchor(project, anchor, paper):
    from scripts.literature_workbench import validate_anchor
    # Reading notes may be useful interpretations, but cannot stand in for the
    # prior author's source when deciding what that work actually reported.
    permitted = {paper["source"]["path"], (paper.get("reader") or {}).get("path")}
    if anchor.get("path") not in permitted:
        raise ValueError("prior axis evidence must cite its registered original source or controlled reader, not notes/reviews")
    return validate_anchor(project, paper, anchor)


def _closest_evaluation(project, evaluation, arm, paper_id, claim_id, library_paper):
    """Bind dataset, metric and evaluation context to actual source values."""
    fields = {"dataset_id", "dataset_version", "metric_definition", "evaluation_basis"}
    if not isinstance(evaluation, dict) or set(evaluation) != fields:
        raise ValueError("quantitative evaluation needs dataset_id, dataset_version, metric_definition and evaluation_basis source bindings")
    checked = {}
    tails = {"dataset_id": {"dataset_id"}, "dataset_version": {"dataset_version", "version"},
             "metric_definition": {"metric", "metric_definition", "definition"},
             "evaluation_basis": {"split", "split_strategy", "evaluation_basis", "analysis_unit", "aggregation"}}
    for field in sorted(fields):
        item = evaluation[field]
        if not isinstance(item, dict):
            raise ValueError("evaluation values must be source bindings")
        value = nonempty(item.get("value"), field)
        if value.strip().casefold() in {"unknown", "not reported", "not_reported", "unclear"}:
            raise ValueError("unknown evaluation values cannot establish a quantitative comparison")
        if arm == "ours":
            # JSON pointers recover actual values from this paper's source
            # protocol/output; two free-form model strings are insufficient.
            bound = bound_source(project, item)
            relative, pointer = bound["path"], item.get("pointer")
            canonical = {f"papers/{paper_id}/{name}" for name in
                         ("experiment-evidence-plan.json", "study-protocol.json", "experiment-evidence.json")}
            manifest = (field in {"dataset_version", "evaluation_basis"} and
                        relative.startswith("data/manifests/") and Path(relative).suffix == ".json")
            if relative not in canonical and not manifest:
                raise ValueError("ours evaluation must bind the actual paper protocol/result JSON")
            if field == "dataset_version" and not manifest:
                raise ValueError("dataset version must bind the actual dataset manifest")
            if not isinstance(pointer, str) or not pointer.startswith("/") or len(pointer) > 1000:
                raise ValueError("ours evaluation needs a bounded JSON pointer")
            tokens = [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]
            if tokens[-1] not in tails[field]:
                raise ValueError("evaluation pointer must identify the actual dataset, metric or evaluation field")
            target = path_in(project, relative)
            if target.stat().st_size > 4_000_000:
                raise ValueError("use a bounded canonical protocol/result JSON")
            selected = read(target)
            if manifest and selected.get("dataset_id") != checked.get("dataset_id", {}).get("value"):
                raise ValueError("dataset manifest must belong to the protocol's bound dataset ID")
            if not manifest and selected.get("paper_id") != paper_id:
                raise ValueError("evaluation protocol/result belongs to a different paper")
            parent_claims = []
            try:
                for token in tokens:
                    if isinstance(selected, dict) and isinstance(selected.get("claim_ids"), list):
                        parent_claims.append(selected["claim_ids"])
                    selected = selected[int(token)] if isinstance(selected, list) and token.isdigit() else selected[token]
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise ValueError("evaluation JSON pointer does not resolve") from exc
            if not isinstance(selected, str) or selected != value:
                raise ValueError("evaluation value differs from its actual protocol/result field")
            if not manifest and not any(claim_id in identifiers for identifiers in parent_claims):
                raise ValueError("evaluation protocol/result field must belong to this actual claim")
            checked[field] = {**bound, "pointer": pointer, "value": selected}
        else:
            bound = _closest_prior_anchor(project, item, library_paper)
            if value not in bound["quote"]:
                raise ValueError("prior evaluation value must occur verbatim in its located original source")
            checked[field] = {**bound, "value": value}
    return checked


def closest_work_axes(project, value, differences):
    """Extend an existing comparison; location checks never certify novelty."""
    if not isinstance(value, dict):
        raise ValueError("closest_work must be an object")
    paper_id, claim_id, work_id = (value.get(key) for key in ("paper_id", "claim_id", "work_id"))
    if not re.fullmatch(r"P[0-9]{2}", str(paper_id)):
        raise ValueError("closest-work comparison needs an actual paper ID")
    nonempty(claim_id, "closest-work claim ID")
    nonempty(work_id, "closest-work work ID")
    context = value.get("context")
    if not isinstance(context, dict) or set(context) != set(CLOSEST_CONTEXT):
        raise ValueError("closest-work context needs novelty matrix, originality audit and literature library bindings")
    documents, bindings = {}, {}
    for key, relative in CLOSEST_CONTEXT.items():
        if not isinstance(context[key], dict) or context[key].get("path") != relative:
            raise ValueError("closest-work context must use the existing canonical " + key)
        bindings[key] = bound_source(project, context[key])
        documents[key] = read(path_in(project, relative))
    matches = [claim for claim in documents["novelty_matrix"].get("claims", [])
               if claim.get("claim_id") == claim_id]
    if (len(matches) != 1 or paper_id not in matches[0].get("paper_ids", []) or
            work_id not in matches[0].get("closest_work_ids", [])):
        raise ValueError("closest-work claim/paper/work relationship is absent from the existing novelty matrix")
    works = [work for work in documents["originality_audit"].get("closest_prior_work", [])
             if work.get("id") == work_id]
    if len(works) != 1:
        raise ValueError("closest-work ID must identify exactly one actual originality-audit work")
    registered = [paper for paper in documents["literature_library"].get("papers", [])
                  if paper.get("id") == value.get("library_work_id")]
    if (len(registered) != 1 or not str(works[0].get("primary_source_url", "")).startswith("https://") or
            registered[0].get("url") != works[0].get("primary_source_url")):
        raise ValueError("closest-work library item must map to that work's registered primary-source URL")
    library_paper = registered[0]
    axes = value.get("axes")
    if not isinstance(axes, dict) or set(axes) != set(CLOSEST_AXES):
        raise ValueError("closest-work comparison must cover research_object, method and result exactly")
    if library_paper.get("source_scope") != "full_text" and any(
            not isinstance(axis, dict) or not isinstance(axis.get("prior"), dict) or
            axis["prior"].get("status") != "unknown" or axis["prior"].get("evidence")
            for axis in axes.values()):
        raise ValueError("closest-work axes need an explicitly full_text source; metadata-only/undeclared leads cannot establish reported work")
    checked, pending = {}, []
    for name in CLOSEST_AXES:
        axis = axes[name]
        if not isinstance(axis, dict):
            raise ValueError("closest-work axis must be an object")
        result = {"scope": nonempty(axis.get("scope"), name + " comparison scope"),
                  "comparison_basis": nonempty(axis.get("comparison_basis"), name + " comparison basis")}
        disposition = axis.get("disposition")
        if disposition not in {"comparable", "not_comparable", "insufficient_evidence"}:
            raise ValueError("each closest-work axis needs an explicit comparability disposition")
        conclusion = axis.get("conclusion_kind")
        if conclusion not in {"descriptive", "superiority", "equivalence", "none"}:
            raise ValueError("closest-work conclusion must be descriptive, superiority, equivalence or none")
        if name != "result" and conclusion in {"superiority", "equivalence"}:
            raise ValueError("research-object/method differences cannot independently establish superiority or equivalence")
        kind = axis.get("result_kind") if name == "result" else None
        if name == "result" and kind not in {"quantitative", "qualitative", "theoretical"}:
            raise ValueError("result axis must distinguish quantitative, qualitative and theoretical results")
        for arm in ("ours", "prior"):
            side = axis.get(arm)
            if not isinstance(side, dict) or side.get("status") not in {"reported", "unknown", "not_reported", "planned"}:
                raise ValueError("axis side must explicitly distinguish reported, planned, unknown or not_reported")
            anchors = side.get("evidence", [])
            if not isinstance(anchors, list) or len(anchors) > 8:
                raise ValueError("axis side evidence must be a bounded list")
            bound = [(_closest_own_anchor(project, anchor, paper_id) if arm == "ours" else
                      _closest_prior_anchor(project, anchor, library_paper)) for anchor in anchors]
            scoped = {"status": side["status"], "scope": nonempty(side.get("scope"), arm + " applicability scope"),
                      "evidence": bound}
            if side["status"] in {"reported", "planned"}:
                scoped["value"] = nonempty(side.get("value"), arm + " axis statement")
                if not bound:
                    raise ValueError("reported/planned closest-work statements need located sources")
                if arm == "prior" and side["status"] == "planned":
                    raise ValueError("use reported author proposal text for prior work, not our planned status")
                if arm == "ours" and name == "result" and side["status"] == "reported" and any(
                        Path(source["path"]).name in {"paper-contract.json", "experiment-evidence-plan.json", "study-protocol.json"}
                        for source in bound):
                    raise ValueError("a planned protocol/contract is not an observed result; use planned or actual result/proof evidence")
            else:
                if side.get("value") is not None:
                    raise ValueError("unknown/not_reported axes cannot supply a claimed result value")
                scoped["missing_reason"] = nonempty(side.get("missing_reason"), arm + " missing information")
            if side["status"] != "reported":
                pending.append(name + "." + arm)
            if name == "result" and kind == "quantitative" and side["status"] == "reported":
                scoped["evaluation"] = _closest_evaluation(project, side.get("evaluation"), arm, paper_id, claim_id, library_paper)
            elif side.get("evaluation") is not None:
                raise ValueError("evaluation bindings belong to reported quantitative results")
            result[arm] = scoped
        incomplete = any(result[arm]["status"] != "reported" for arm in ("ours", "prior"))
        if incomplete and (disposition == "comparable" or conclusion in {"superiority", "equivalence"}):
            raise ValueError("planned/unknown/not_reported evidence cannot establish comparability or a comparative benefit")
        same_evaluation = None
        if name == "result" and kind == "quantitative" and not incomplete:
            same_evaluation = all(result["ours"]["evaluation"][key]["value"] ==
                                  result["prior"]["evaluation"][key]["value"]
                                  for key in ("dataset_id", "dataset_version", "metric_definition", "evaluation_basis"))
            if not same_evaluation and (disposition == "comparable" or conclusion in {"superiority", "equivalence"}):
                raise ValueError("different source-bound datasets, metrics or evaluation bases cannot establish superiority/equivalence")
        if conclusion in {"superiority", "equivalence"} and (
                name != "result" or kind != "quantitative" or disposition != "comparable" or differences):
            raise ValueError("comparative benefit needs source-bound matched quantitative evaluation and matched declared conditions")
        result.update(disposition=disposition, conclusion_kind=conclusion,
                      source_location_check="needs_inputs" if incomplete else "source_bound",
                      semantic_support_verified=False, comparability_verified=False)
        if name == "result":
            result.update(result_kind=kind, same_bound_evaluation_values=same_evaluation)
        checked[name] = result
    return {"paper_id": paper_id, "claim_id": claim_id, "work_id": work_id,
            "library_work_id": value["library_work_id"], "primary_source_url": works[0]["primary_source_url"],
            "context": bindings, "axes": checked, "pending_axes": pending,
            "record_complete": True,
            "source_location_check": "needs_inputs" if pending else "source_bound",
            "scientific_comparability_verified": False, "novelty_verified": False,
            "independent_review_required": True}


def comparison(project, row):
    question = nonempty(row.get("question"), "question")
    arms = {}
    for arm in ("left", "right"):
        item = row[arm]
        arms[arm] = {"evidence": sources(project, item.get("evidence")),
                     "conditions": {key: nonempty(item["conditions"].get(key), key) for key in DIMENSIONS}}
    differences = [key for key in DIMENSIONS if arms["left"]["conditions"][key] != arms["right"]["conditions"][key]]
    unknowns = [f"{arm}.{key}" for arm in arms for key in DIMENSIONS
                if arms[arm]["conditions"][key].strip().lower() in {"unknown", "not reported", "unclear"}]
    disposition = row.get("disposition")
    if disposition not in {"comparable", "not_comparable", "insufficient_evidence"}:
        raise ValueError("comparison needs an explicit comparability disposition")
    if disposition == "comparable" and unknowns:
        raise ValueError("unknown conditions cannot establish comparability")
    explanations = row.get("difference_explanations", {})
    for key in differences:
        nonempty(explanations.get(key), f"explanation for {key}")
    test = row.get("discriminating_test")
    if test is not None:
        for key in ("hypothesis", "design", "observable", "failure_condition", "stop_rule"):
            nonempty(test.get(key), key)
        predictions = test.get("predictions")
        if not isinstance(predictions, list) or len(predictions) != 2:
            raise ValueError("a discriminating test needs two competing predictions")
        for prediction in predictions:
            nonempty(prediction.get("explanation"), "competing explanation")
            nonempty(prediction.get("expected_observation"), "expected observation")
        if predictions[0]["expected_observation"] == predictions[1]["expected_observation"]:
            raise ValueError("identical predictions cannot discriminate explanations")
    result = {**row, **arms, "question": question, "different_conditions": differences,
            "unknown_conditions": unknowns, "comparability_verified": False,
            "conflict_resolution_verified": False, "experiment_executed": False}
    result["closest_work_axis_check"] = "not_assessed"
    if "closest_work" in row:
        result["closest_work"] = closest_work_axes(project, row["closest_work"], differences)
        result["closest_work_axis_check"] = result["closest_work"]["source_location_check"]
    return result


def method(project, row):
    if not re.fullmatch(r"P[0-9]{2}", row.get("paper_id", "")):
        raise ValueError("method adoption needs paper ID")
    contract = read(path_in(project, f"papers/{row['paper_id']}/paper-contract.json"))
    nonempty(contract.get("research_question"), "actual paper research question")
    for key in ("baseline_class", "fair_comparison", "resource_rationale", "transfer_limitations"):
        nonempty(row.get(key), key)
    if row["baseline_class"] not in {"simple", "domain-standard", "strong-recent"}:
        raise ValueError("unknown baseline class")
    from scripts.method_tools import inspect
    report = inspect(project)
    if report["errors"]:
        raise ValueError("method contracts are blocked: " + "; ".join(report["errors"]))
    selected = next((item for item in report["tools"] if item["id"] == row.get("method_tool_id")), None)
    if selected is None:
        raise ValueError("method adoption requires a registered pinned method tool")
    design = read(path_in(project, row["design_path"]))
    if not row["design_path"].startswith(f"papers/{row['paper_id']}/experiments/"):
        raise ValueError("method design belongs to a different paper")
    baseline = next((b for b in design.get("baselines", []) if b.get("id") == row.get("baseline_id")), None)
    if baseline is None:
        raise ValueError("method adoption must bind an actual baseline in the design")
    if baseline.get("class") != row["baseline_class"].replace("-", "_"):
        raise ValueError("method baseline class differs from the actual design")
    if not set(selected["run_ids"]).issubset(set(design.get("run_ids", []))):
        raise ValueError("method validation runs must belong to the declared design")
    return {**row, "evidence": sources(project, row.get("evidence")),
            "contract_sha256": sha(path_in(project, f"papers/{row['paper_id']}/paper-contract.json")),
            "design_sha256": sha(path_in(project, row["design_path"])),
            "qualification": selected["qualification"], "scientific_applicability_verified": False}


def reading_anchor(project, row):
    from scripts.output_provenance import current_origin
    receipt = bound_source(project, row["reader_receipt"])
    receipt_path = path_in(project, receipt["path"])
    origin = current_origin(project, receipt_path)
    if origin.get("status") != "tracked" or not receipt["path"].startswith("literature/readers/"):
        raise ValueError("reading anchor requires a current controlled reader receipt")
    value = read(receipt_path)
    pdf = bound_source(project, row["pdf"])
    if pdf["sha256"] != value.get("pdf_sha256"):
        raise ValueError("reader and PDF differ")
    source_map = value["source_map"]
    if sha(path_in(project, source_map["path"])) != source_map["sha256"]:
        raise ValueError("reader source map changed")
    page = row.get("page")
    if type(page) is not int or not 1 <= page <= value["page_count"]:
        raise ValueError("anchor page is outside the real PDF")
    if page not in {block["pdf_page"] for block in read(path_in(project, source_map["path"]))["source_blocks"]}:
        raise ValueError("anchor page was not in the actual reader scope")
    if row.get("kind") not in {"figure", "table", "equation", "assumption", "claim"}:
        raise ValueError("unsupported reading anchor")
    nonempty(row.get("label"), "original figure/table/formula label")
    nonempty(row.get("interpretation"), "separate interpretation")
    nonempty(row.get("inference_boundary"), "inference boundary")
    import fitz
    with fitz.open(path_in(project, pdf["path"])) as document:
        actual = document[page - 1]
        quote = row.get("quote")
        if quote:
            if nonempty(quote, "quote") not in actual.get_text():
                raise ValueError("reading quote is absent from the specified PDF page")
        else:
            box = row.get("bbox")
            if (not isinstance(box, list) or len(box) != 4 or
                    any(type(x) not in {int, float} for x in box) or
                    not 0 <= box[0] < box[2] <= actual.rect.width or
                    not 0 <= box[1] < box[3] <= actual.rect.height):
                raise ValueError("non-text anchor needs an actual bounded PDF rectangle")
    return {**row, "pdf": pdf, "reader_receipt": receipt,
            "source_map": source_map, "semantic_verification": "needs_human_review",
            "numerical_data_reconstructed": False}


def review(project, row, previous=None):
    if row.get("perspective") not in PERSPECTIVES:
        raise ValueError("review perspective must be method, statistics or contribution")
    nonempty(row.get("question"), "review question")
    if row.get("severity") not in {"fatal", "major", "minor"}:
        raise ValueError("review severity required")
    if row.get("status") not in {"open", "answered_pending_review", "verified_resolved"}:
        raise ValueError("review finding status required")
    if (previous or {}).get("writing_action_assessment", {}).get("status") not in {None, "not_assessed"}:
        severity_rank = {"minor": 0, "major": 1, "fatal": 2}
        if severity_rank[row["severity"]] < severity_rank[previous["severity"]]:
            raise ValueError("Do not downgrade an inherited structured issue severity to bypass unresolved work")
        if row["perspective"] != previous["perspective"]:
            raise ValueError("Keep inherited structured issue perspective stable")
    result = {**row, "evidence": sources(project, row.get("evidence")),
              "independent_raters_verified": False}
    from scripts.writing_review_actions import assess
    result["writing_action_assessment"] = assess(project, row.get("writing_action"),
        previous=(previous or {}).get("writing_action_assessment"))
    nonempty(row.get("required_action"), "required experiment or evidence")
    if row["status"] != "open":
        result["response_evidence"] = sources(project, row.get("response_evidence"))
    if row["status"] == "verified_resolved":
        # A model-authored status cannot certify its own resolution.
        raise ValueError("use answered_pending_review; resolution needs the existing independent audit and human gate")
    return result


def audit(project: Path) -> dict:
    previous = {}
    saved_path = path_in(project, OUTPUT, exists=False)
    if saved_path.is_file():
        from scripts.output_provenance import current_origin
        origin = current_origin(project, saved_path)
        if origin.get("status") != "tracked" or origin.get("provider") != "deterministic-control-plane":
            raise ValueError("research extension audit provenance changed")
        saved = read(saved_path)
        previous = {row["id"]: row for row in [*saved.get("retained_review_findings", []),
            *saved.get("sections", {}).get("review_findings", [])]}
    path = path_in(project, INPUT, exists=False)
    if not path.is_file():
        retained = [row for row in previous.values()
                    if row.get("writing_action_assessment", {}).get("status") not in {None, "not_assessed"}]
        return {"schema_version": "1.0", "status": "blocked" if retained else "needs_inputs",
                "errors": ["Do not delete the research extensions input containing existing structured writing issues"] if retained else [],
                "sections": {}, "retained_review_findings": retained, "pending": [INPUT],
                "scientific_completion_verified": False, "gate_approved": False}
    document = read(path)
    if document.get("schema_version") != "1.0":
        raise ValueError("unsupported research extensions schema")
    output = {"schema_version": "1.0", "input_sha256": sha(path), "sections": {}, "errors": [],
              "scientific_completion_verified": False, "gate_approved": False}
    for section, builder in {"comparisons": comparison, "methods": method,
                             "reading_anchors": reading_anchor, "review_findings": review}.items():
        rows = document.get(section, [])
        if not isinstance(rows, list) or len(rows) > 200:
            raise ValueError("research extension section must have at most 200 rows")
        seen, checked = set(), []
        for row in rows:
            if not isinstance(row, dict):
                output["errors"].append(f"{section}: row must be an object")
                continue
            try:
                identifier = row.get("id")
                if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", identifier) or identifier in seen:
                    raise ValueError("unique bounded row ID required")
                seen.add(identifier)
                checked.append(builder(project, row, previous.get(identifier)) if section == "review_findings" else builder(project, row))
            except (KeyError, ValueError, TypeError, OSError, RuntimeError) as exc:
                output["errors"].append(f"{section}/{row.get('id', '?')}: {exc}")
        output["sections"][section] = checked
    current_issues = {row["id"] for row in output["sections"].get("review_findings", [])}
    output["retained_review_findings"] = [row for key, row in previous.items() if key not in current_issues
        and row.get("writing_action_assessment", {}).get("status") not in {None, "not_assessed"}]
    if any(row.get("writing_action_assessment", {}).get("status") not in {None, "not_assessed"}
           for key, row in previous.items() if key not in current_issues):
        output["errors"].append("Do not silently delete an existing structured writing issue; retain its disposition and history")
    output["pending"] = [name for name, rows in output["sections"].items() if not rows]
    output["status"] = "blocked" if output["errors"] else "needs_scientific_review"
    return output


def refresh(project: Path) -> dict:
    value = audit(project)
    path = path_in(project, OUTPUT, exists=False)
    write(path, value)
    record(project, [path], "scripts/research_extensions.py")
    return value


def gate_errors(project: Path) -> list[str]:
    try:
        result = audit(project)
        return result["errors"] + [f"{row['id']}: unresolved {row['perspective']} finding"
            for row in result.get("sections", {}).get("review_findings", [])
            if row["severity"] in {"fatal", "major"} and (row["status"] == "open"
                or row.get("writing_action_assessment", {}).get("status") == "pending_materials")]
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        return [str(exc)]
