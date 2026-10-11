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
    return {**row, **arms, "question": question, "different_conditions": differences,
            "unknown_conditions": unknowns, "comparability_verified": False,
            "conflict_resolution_verified": False, "experiment_executed": False}


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


def review(project, row):
    if row.get("perspective") not in PERSPECTIVES:
        raise ValueError("review perspective must be method, statistics or contribution")
    nonempty(row.get("question"), "review question")
    if row.get("severity") not in {"fatal", "major", "minor"}:
        raise ValueError("review severity required")
    if row.get("status") not in {"open", "answered_pending_review", "verified_resolved"}:
        raise ValueError("review finding status required")
    result = {**row, "evidence": sources(project, row.get("evidence")),
              "independent_raters_verified": False}
    nonempty(row.get("required_action"), "required experiment or evidence")
    if row["status"] != "open":
        result["response_evidence"] = sources(project, row.get("response_evidence"))
    if row["status"] == "verified_resolved":
        # A model-authored status cannot certify its own resolution.
        raise ValueError("use answered_pending_review; resolution needs the existing independent audit and human gate")
    return result


def audit(project: Path) -> dict:
    path = path_in(project, INPUT, exists=False)
    if not path.is_file():
        return {"status": "needs_inputs", "errors": [], "pending": [INPUT],
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
                checked.append(builder(project, row))
            except (KeyError, ValueError, TypeError, OSError, RuntimeError) as exc:
                output["errors"].append(f"{section}/{row.get('id', '?')}: {exc}")
        output["sections"][section] = checked
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
    if not (project / INPUT).exists():
        return []
    try:
        result = audit(project)
        return result["errors"] + [f"{row['id']}: unresolved {row['perspective']} finding"
            for row in result.get("sections", {}).get("review_findings", [])
            if row["severity"] in {"fatal", "major"} and row["status"] == "open"]
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        return [str(exc)]
