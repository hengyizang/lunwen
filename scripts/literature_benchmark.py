"""Read-only retrieval/answer/extraction comparison against explicit source labels.

No model calls or automatic route promotion. Gold labels are attributed inputs,
not scientific approval; semantic support stays pending without actual review.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import time

from scripts import evidence_retrieval, literature_review, literature_workbench as workbench
from scripts.research_artifacts import path_in, record, sha, write

OUTPUT = "reports/literature-benchmark/latest.json"


def _bound_json(project, binding, prefix):
    if (not isinstance(binding, dict) or not isinstance(binding.get("path"), str)
            or not binding["path"].startswith(prefix)):
        raise ValueError("benchmark result must name a bounded " + prefix + " artifact")
    target = workbench._path(project, binding["path"])
    if target.stat().st_size > 4_000_000 or sha(target) != binding.get("sha256"):
        raise ValueError("benchmark artifact changed or is oversized")
    from scripts.output_provenance import current_origin
    if current_origin(project, target).get("status") != "tracked":
        raise ValueError("benchmark artifact needs current execution provenance")
    return workbench._json(target.read_bytes())


def _recall(results, anchors):
    hits = sum(any(row["path"] == a["path"] and row["sha256"] == a["sha256"]
        and row["start_line"] <= a["start_line"] <= a["end_line"] <= row["end_line"] for row in results)
        for a in anchors)
    return {"located_gold_anchors": hits, "gold_anchors": len(anchors),
            "recall": hits / len(anchors) if anchors else None}


def _number(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 100:
        raise ValueError("gold numeric values must be explicit decimal strings")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("invalid gold decimal") from exc
    if not result.is_finite():
        raise ValueError("gold decimal must be finite")
    return result


def evaluate(project: Path, spec: dict) -> dict:
    if (not isinstance(spec, dict) or spec.get("schema_version") != "1.0"
            or set(spec) - {"schema_version", "annotation", "cases", "numeric_cases", "cost_scope"}):
        raise ValueError("unsupported literature benchmark")
    annotation = spec.get("annotation")
    if (not isinstance(annotation, dict) or annotation.get("kind") not in {"synthetic_fixture", "primary_source_fixture", "human_annotation"}
            or not isinstance(annotation.get("by"), str) or not annotation["by"].strip()):
        raise ValueError("attribute gold labels; synthetic fixtures are not scientific validation")
    cases = spec.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 50:
        raise ValueError("benchmark needs 1..50 explicit cases")
    library, _, _ = workbench._snapshot(project)
    papers = {p["id"]: p for p in library["papers"] if p.get("status") == "current"}
    seen, reports = set(), []
    for case in cases:
        if (not isinstance(case, dict) or set(case) - {"id", "request", "relevant", "qa_report", "expected_abstain"}
                or workbench._id(case.get("id")) in seen):
            raise ValueError("benchmark cases need distinct IDs and bounded fields")
        seen.add(case["id"])
        prepared = literature_review.prepare(project, case["request"])
        anchors = case.get("relevant")
        if not isinstance(anchors, list) or len(anchors) > 100:
            raise ValueError("explicit relevant source anchors are required, empty for missing-evidence cases")
        unique_anchors = set()
        for anchor in anchors:
            if not isinstance(anchor, dict) or anchor.get("paper_id") not in case["request"]["paper_ids"]:
                raise ValueError("gold anchor must belong to a selected paper")
            checked_anchor = workbench.validate_anchor(project, papers[anchor["paper_id"]], {k: v for k, v in anchor.items() if k != "paper_id"})
            identity = (anchor["paper_id"], *(checked_anchor.get(k) for k in
                ("path", "sha256", "start_line", "end_line", "quote", "pdf_page")))
            if identity in unique_anchors:
                raise ValueError("duplicate gold evidence anchor would distort recall")
            unique_anchors.add(identity)
        baseline = {k: v for k, v in prepared["spec"].items() if k not in {"query_expansions", "dense_cache", "rerank_cache"}}
        started = time.perf_counter()
        first = evidence_retrieval.retrieve(project, baseline)
        first_time = time.perf_counter() - started
        started = time.perf_counter()
        second = evidence_retrieval.retrieve(project, prepared["spec"])
        row = {"id": case["id"], "request_sha256": workbench._digest(case["request"]),
            "baseline": {**_recall(first["results"], anchors), "elapsed_seconds": first_time},
            "candidate": {**_recall(second["results"], anchors), "elapsed_seconds": time.perf_counter() - started},
            "same_corpus": [{k: s.get(k) for k in ("path", "sha256", "ranges")} for s in first["searched_sources"]]
                == [{k: s.get(k) for k in ("path", "sha256", "ranges")} for s in second["searched_sources"]],
            "semantic_support": "not_measured_requires_source_review", "paid_calls": 0}
        if "qa_report" in case:
            answer = _bound_json(project, case["qa_report"], "evidence/qa/")
            if answer.get("question") != prepared["question"]:
                raise ValueError("answer question differs from this benchmark case")
            expected = {(s["path"], s["sha256"]) for s in prepared["spec"]["sources"]}
            actual = {(s["path"], s["sha256"]) for s in answer.get("retrieval", {}).get("sources", [])}
            if actual != expected:
                raise ValueError("answer source/version scope differs from benchmark")
            source_ids = {s["source_id"]: s for s in answer["retrieval"]["sources"]}
            selected_sources = {s["path"]: s for s in prepared["spec"]["sources"]}
            for block in answer["retrieval"].get("blocks", []):
                source = source_ids.get(block.get("source_id"))
                match = re.fullmatch(r"(?:PDF page ([1-9][0-9]*), )?lines ([1-9][0-9]*)-([1-9][0-9]*)", block.get("locator", ""))
                if source is None or match is None:
                    raise ValueError("answer block needs current original line/page ranges")
                page, start, end = (int(v) if v is not None else None for v in match.groups())
                ranges = selected_sources[source["path"]]["ranges"]
                if not any(r["start_line"] <= start <= end <= r["end_line"] and r.get("pdf_page") == page for r in ranges):
                    raise ValueError("answer block lies outside current original ranges")
                original = workbench._Files(project).text(source["path"]).splitlines()
                span = "\n".join(original[start - 1:end])
                if not block.get("text") or block["text"].rstrip("\n") != span:
                    raise ValueError("answer block does not match original source bytes")
            from scripts.paper_qa import validate_response
            import json
            response = answer.get("response")
            checked = validate_response(json.dumps(response), answer["retrieval"]["blocks"])
            expectation = case.get("expected_abstain")
            if type(expectation) is not bool:
                raise ValueError("answer comparison needs an explicit expected abstention")
            row["answer"] = {"citation_integrity": True, "abstention_matches_label": checked["abstain"] == expectation,
                "statement_mapping_present": "statements" in checked, "semantic_support_verified": False}
        reports.append(row)
    numeric_cases = spec.get("numeric_cases", [])
    if not isinstance(numeric_cases, list) or len(numeric_cases) > 100:
        raise ValueError("at most 100 numeric comparison cells")
    numbers = []
    for item in numeric_cases:
        if (not isinstance(item, dict) or set(item) - {"id", "matrix", "paper_id", "field_id", "expected_value", "expected_unit", "expected_comparator"}
                or not {"id", "matrix", "paper_id", "field_id", "expected_value", "expected_unit"} <= set(item)):
            raise ValueError("numeric labels need exact matrix cell/value/unit")
        workbench._id(item["id"])
        if item["id"] in {n["id"] for n in numbers}:
            raise ValueError("duplicate numeric comparison ID")
        if item["matrix"].get("path") != "reports/literature-matrix/matrix.json":
            raise ValueError("numeric benchmark needs the canonical current literature matrix")
        from scripts.literature_matrix import validate_saved_report
        manifest = workbench._json(path_in(project, "reports/literature-matrix/manifest.json").read_bytes())
        validate_saved_report(project, manifest["request"]["path"])
        matrix = _bound_json(project, item["matrix"], "reports/literature-matrix/")
        cells = [c for c in matrix.get("cells", []) if c.get("paper_id") == item["paper_id"] and c.get("field_id") == item["field_id"]]
        if len(cells) != 1:
            raise ValueError("numeric benchmark cell missing or ambiguous")
        numeric = cells[0].get("numeric") or {}
        value = numeric.get("value")
        comparator = item.get("expected_comparator", "=")
        if comparator not in {"=", "<", "<=", ">", ">="}:
            raise ValueError("invalid gold comparator")
        matches = (value is not None and _number(str(value)) == _number(item["expected_value"])
            and numeric.get("unit") == item["expected_unit"] and numeric.get("comparator") == comparator)
        numbers.append({"id": item["id"], "matches_gold_value_and_unit": matches,
            "source_semantics_verified": False, "visual_status": cells[0].get("source_context", {}).get("visual_status", "unknown")})
    costs = None
    if "cost_scope" in spec:
        scope = spec["cost_scope"]
        if not isinstance(scope, dict) or set(scope) - {"cost_run_ids", "additional_cost_receipts"}:
            raise ValueError("use actual scoped runtime cost receipts")
        runs = scope.get("cost_run_ids", [])
        if not isinstance(runs, list) or len(runs) > 200 or any(not isinstance(r, str) for r in runs) or len(set(runs)) != len(runs):
            raise ValueError("cost scope needs distinct existing run IDs")
        from scripts.calibration_analysis import cost_summary
        costs = cost_summary(project, scope, {"answer_key": []}, 0)
    return {"schema_version": "1.0", "kind": "literature_quality_cost_benchmark", "annotation": annotation,
        "cases": reports, "numeric_cases": numbers, "recorded_costs": costs,
        "evaluation_paid_calls": 0, "precomputed_index_cost_included": False,
        "total_cost_verified": False, "automatic_route_promotion": False,
        "scientific_validity_verified": False, "labels_are_independent_scientific_review": False}


def refresh(project: Path, request_file="program/literature-benchmark.json") -> dict:
    if not isinstance(request_file, str) or not request_file.startswith("program/"):
        raise ValueError("benchmark specification belongs under program/")
    source = workbench._path(project, request_file)
    if source.stat().st_size > 1_000_000:
        raise ValueError("benchmark specification exceeds 1 MB")
    report = evaluate(project, workbench._json(source.read_bytes()))
    report["request"] = {"path": request_file, "sha256": sha(source)}
    report["implementation_sha256"] = sha(Path(__file__))
    target = path_in(project, OUTPUT, exists=False)
    write(target, report)
    record(project, [target], "scripts/literature_benchmark.py")
    return {"report": OUTPUT, **report}


def judgment_benchmark(project: Path, spec: dict, *, observed=None) -> dict:
    """Measure retained predictions against attributed public-review anchors.

    No anchor, rating or license is generated. Twenty to thirty distinct actual
    papers form the requested calibration design; synthetic labels never count
    towards that design and missing predictions leave accuracy unknown.
    """
    from scripts.research_artifacts import bound_source, read
    from scripts.output_provenance import current_origin
    if not isinstance(spec, dict) or set(spec) - {"schema_version", "id", "anchor_set", "predictions", "paper_id"} or spec.get("schema_version") != "1.0":
        raise ValueError("unsupported judgment benchmark")
    bound = bound_source(project, spec["anchor_set"])
    anchor_file = path_in(project, bound["path"])
    if anchor_file.stat().st_size > 2_000_000:
        raise ValueError("anchor set exceeds 2 MB")
    anchors = read(anchor_file)
    if anchors.get("kind") not in {"public_review", "synthetic_fixture"}:
        raise ValueError("attribute actual public reviews or explicitly synthetic fixtures")
    labels, cases, partitions, paper_partitions = {}, [], {}, {}
    incoming = anchors.get("cases")
    if not isinstance(incoming, list) or not 1 <= len(incoming) <= 200:
        raise ValueError("anchor set needs bounded source-located cases")
    for row in incoming:
        key = workbench._id(row.get("id"))
        if key in labels or row.get("partition") not in {"calibration", "holdout"}:
            raise ValueError("distinct anchor IDs and explicit partitions are required")
        source = bound_source(project, row["source"])
        target = path_in(project, source["path"])
        quote = workbench._text(row.get("quote"), "public review quote")
        if target.stat().st_size > 4_000_000 or quote not in target.read_text(encoding="utf-8"):
            raise ValueError("anchor quote must occur in its exact original public review")
        if row.get("label") not in {"supports", "contradicts", "insufficient", "distinct", "should_merge"}:
            raise ValueError("unsupported actual anchor label")
        doi = workbench._text(row.get("paper_doi"), "original paper DOI")
        from scripts.citation_audit import normalize_doi
        doi = normalize_doi(doi)
        if not re.fullmatch(r"10\.\d{4,9}/\S+", doi, re.I):
            raise ValueError("anchor paper needs a valid DOI identity; arbitrary labels cannot count as distinct papers")
        partition = row["partition"]
        for identity, mapping in ((source["sha256"], partitions), (doi, paper_partitions)):
            if identity in mapping and mapping[identity] != partition:
                raise ValueError("the same paper/review cannot leak across calibration and holdout")
            mapping[identity] = partition
        if anchors["kind"] == "public_review":
            review = bound_source(project, row["review"])
            review_file = path_in(project, review["path"])
            review_quote = workbench._text(row.get("review_quote"), "original public review label basis")
            if review_file.stat().st_size > 4_000_000 or review_quote not in review_file.read_text(encoding="utf-8"):
                raise ValueError("review label needs a verbatim original public-review anchor")
            for original in (target, review_file):
                origin = current_origin(project, original)
                if origin.get("status") != "tracked" or origin.get("provider") not in {"deterministic-control-plane", "human-attestation"}:
                    raise ValueError("model-authored or untracked text cannot become a real review anchor")
            if review["sha256"] in partitions and partitions[review["sha256"]] != partition:
                raise ValueError("the same public review cannot leak across partitions")
            partitions[review["sha256"]] = partition
            rights = bound_source(project, row["rights"])
            rights_file = path_in(project, rights["path"])
            declaration = read(rights_file)
            if (declaration.get("reuse_allowed") is not True or not str(declaration.get("license_url", "")).startswith("https://")
                    or declaration.get("review_sha256") != review["sha256"] or declaration.get("paper_source_sha256") != source["sha256"]):
                raise ValueError("actual public-review license evidence is required")
            if not str(row.get("review_url", "")).startswith("https://"):
                raise ValueError("real review anchors require their original public URL")
        labels[key] = row["label"]
        cases.append({"id": key, "paper_doi": doi, "partition": partition, "source": source,
            "quote": quote, "question": workbench._text(row.get("question"), "blind evidence question")})
    evaluations, bindings, retained = [], [], []
    for binding in spec.get("predictions", []):
        checked = bound_source(project, binding)
        path = path_in(project, checked["path"])
        origin = current_origin(project, path)
        if origin.get("status") != "tracked" or origin.get("role") not in {"independent-critic", "independent-critic-initial", "independent-critic-final", "review-panel-response"}:
            raise ValueError("benchmark predictions need retained actual independent-review provenance")
        retained.append((checked, read(path), origin.get("model")))
    if observed is None and spec.get("paper_id"):
        from scripts.literature_source_tasks import judgment_responses
        observed = judgment_responses(project, spec["paper_id"])
    for row in observed or []:
        if "anchor_labels" in row["response"]:
            receipt = row["receipt"]
            checked = bound_source(project, {**receipt["response"], "locator": "actual independent anchor response"})
            if not any(prior[0]["path"] == checked["path"] for prior in retained):
                retained.append((checked, row["response"], receipt["identity"]["requested_model"]))
    for checked, payload, model in retained:
        predictions = {}
        for row in payload.get("anchor_labels", []):
            if row.get("case_id") not in labels or row.get("case_id") in predictions or row.get("outcome") not in {"supports", "contradicts", "insufficient", "distinct", "should_merge"}:
                raise ValueError("duplicate or out-of-scope benchmark prediction")
            predictions[row["case_id"]] = row["outcome"]
        bindings.append(checked)
        results = {}
        for partition in ("calibration", "holdout"):
            ids = [r["id"] for r in cases if r["partition"] == partition]
            complete = bool(ids) and all(key in predictions for key in ids)
            results[partition] = {"cases": len(ids), "predictions": sum(key in predictions for key in ids),
                "agreement": sum(predictions.get(key) == labels[key] for key in ids) / len(ids) if complete else None}
        merge_ids = [key for key, label in labels.items() if label == "should_merge"]
        evaluations.append({"prediction": checked, "model": model, "partitions": results,
            "should_merge_detection": sum(predictions.get(k) == "should_merge" for k in merge_ids) / len(merge_ids)
                if merge_ids and all(k in predictions for k in merge_ids) else None})
    return {"schema_version": "1.0", "operation": "judgment_benchmark", "id": workbench._id(spec["id"]),
        "anchor_set": bound, "annotation_kind": anchors["kind"], "blind_cases": cases, "prediction_sources": bindings,
        "results": evaluations, "attributed_public_paper_count": len(paper_partitions) if anchors["kind"] == "public_review" else 0,
        "requested_anchor_design_complete": anchors["kind"] == "public_review" and 20 <= len(paper_partitions) <= 30 and set(paper_partitions.values()) == {"calibration", "holdout"},
        "calibration_status": "NOT_CALIBRATED", "model_call_made": False, "scientific_completion_verified": False,
        "role_contract": "Use blind_cases only; never inspect anchor labels or the answer-key source. Return anchor_labels:[{case_id,outcome,rationale}]. Preserve insufficient and should_merge; agreement on attributed reviews is not scientific validity, a quality score calibration or an acceptance probability."}
