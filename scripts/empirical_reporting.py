"""Archive complete sealed estimates; check only declared manuscript statistics.

No fit is launched here. Deterministic recomputation checks the reviewed runtime
against actual approved outputs; scientific identification remains human work.
"""
from __future__ import annotations

import csv
import io
import math
import re
from pathlib import Path

from scripts.research_artifacts import path_in, read, record, sha, write

MODULE = "scripts/empirical_reporting.py"
FIELDS = ("estimate", "standard_error", "ci_low", "ci_high", "confidence_level",
          "p_value", "p_adjusted", "n_observations", "n_units")


from scripts.paper_execution import paper_scoped

def _need(ok, message):
    if not ok:
        raise ValueError(message)


def _same(actual, expected):
    if isinstance(expected, bool):
        return type(actual) is bool and actual == expected
    if type(expected) in (int, float):
        return type(actual) in (int, float) and math.isfinite(actual) and math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-12)
    if isinstance(expected, dict):
        return isinstance(actual, dict) and actual.keys() == expected.keys() and all(_same(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(_same(a, b) for a, b in zip(actual, expected))
    return actual == expected


@paper_scoped
def measured(project: Path, paper_id: str, specification_id: str) -> dict:
    from scripts import empirical_design, empirical_runtime
    from scripts.figure_provenance import run_seal
    design_check = empirical_design.audit(project, paper_id, require_frozen=True)
    _need(not design_check.get("errors"), "empirical design is blocked: " + "; ".join(design_check.get("errors", [])))
    card_path = path_in(project, f"papers/{paper_id}/empirical-design.json")
    card = read(card_path)
    specs = [s for s in card["specifications"] if s["id"] == specification_id]
    _need(len(specs) == 1, "an exact empirical specification ID is required")
    spec = specs[0]
    seal = run_seal(project, paper_id, spec["run_id"])
    source = next((r for r in seal["outputs"] if r["path"] == spec["output"]), None)
    _need(source is not None, "empirical estimate is not an approved executor output")
    output = read(path_in(project, spec["output"]))
    expected = empirical_runtime.calculate(card, spec, path_in(project, card["data"]["path"]), design_path=card_path)
    _need(_same(output, expected), "empirical result differs from deterministic estimator recomputation")
    _need(output.get("scientific_validity_verified") is False, "an estimator cannot certify causal validity")
    return {"specification": spec, "result": output, "source": source, "executor": seal}


@paper_scoped
def _diagnostics(project, paper_id, card):
    from scripts.figure_provenance import run_seal
    bindings = []
    for diagnostic in card["diagnostics"]:
        seal = run_seal(project, paper_id, diagnostic["run_id"])
        output = next((r for r in seal["outputs"] if r["path"] == diagnostic["output"]), None)
        _need(output is not None, "diagnostic needs its exact approved output")
        payload = read(path_in(project, output["path"]))
        _need(payload.get("diagnostic_id") == diagnostic["id"] and type(payload.get("passed")) is bool,
              "diagnostic output needs its registered ID and an explicit computed outcome")
        _need(isinstance(payload.get("details"), dict) and payload["details"], "diagnostic needs actual check details")
        _need(payload["passed"], "diagnostic failed; follow its predeclared failure_action: " + diagnostic["id"])
        bindings.append({"id": diagnostic["id"], **output, "executor": seal,
                         "scientific_assumption_verified": False})
    return bindings


def table_bytes(rows):
    fields = ["specification_id", "method", "phase", "family", *FIELDS]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows({k: row[k] for k in fields} for row in rows)
    return stream.getvalue().encode("utf-8")


def _presented_specifications(project, paper_id, rows):
    """Trace explicit statistics and existing fact/claim sources, not shared numbers."""
    from scripts.ref_verify_adapter import canonical_manuscript
    from scripts.citation_audit import citation_prose, tex_source_paths
    from scripts.manuscript_language import extract_text
    paper = project / "papers" / paper_id
    if not any((paper / "manuscript" / name).is_file() for name in ("main.tex", "main.docx")):
        return set(), []
    canonical = canonical_manuscript(paper)
    sources = tex_source_paths(canonical) if canonical.suffix == ".tex" else [canonical]
    if canonical.suffix == ".tex":
        from scripts.tex_sources import expand
        content = citation_prose(expand(canonical).text, tex=True)
    else:content = citation_prose(extract_text(canonical))
    fields = r"(?:estimate|standard[_ ]error|ci[_ ](?:low|high)|confidence[_ ]level|p[_ ](?:value|adjusted)|n[_ ](?:observations|units)|phase)"
    presented = {row["specification_id"] for row in rows if re.search(
        r"(?<![\w.-])" + re.escape(row["specification_id"]) + r"(?![\w.-])\s+" + fields + r"\s*[:=]", content, re.I)}
    facts_path = paper / "reviews/paper-facts.json"
    if facts_path.is_file():
        sources = [*sources, facts_path]
        facts = read(facts_path)
        def quote(value):
            value = citation_prose(str(value or ""), tex=True)
            return value if re.search(r"\b[A-Za-z]{2,}\b|[\u4e00-\u9fff]", value) else ""
        claims = facts.get("claim_alignment", [])
        result_quotes = [quote(claim.get("sections", {}).get("results")) for claim in claims]
        used = {key for claim, current in zip(claims, result_quotes)
            if current and result_quotes.count(current) == 1 and current in content for key in claim.get("evidence_ids", [])}
        statements = {}
        for fact in facts.get("facts", []):
            current = quote(fact.get("statement"))
            if current:statements.setdefault(current, set()).add(fact.get("source_path"))
        paths = {fact.get("source_path") for fact in facts.get("facts", []) if fact.get("id") in used or (
            quote(fact.get("statement")) in content and statements.get(quote(fact.get("statement"))) == {fact.get("source_path")})}
        presented.update(row["specification_id"] for row in rows if row["source"]["path"] in paths)
    return presented, [{"path": source.relative_to(project).as_posix(), "sha256": sha(source)} for source in sorted(sources)]


@paper_scoped
def _map_errors(project, paper_id, rows, *, require_mapping):
    mapping_path = project/f"papers/{paper_id}/empirical-reporting-map.json"
    if not mapping_path.is_file():
        return (["empirical manuscript reporting map is required"] if require_mapping else []), [], []
    mapping = read(mapping_path)
    _need(mapping.get("paper_id") == paper_id and mapping.get("schema_version") == "1.0", "invalid empirical reporting map identity")
    indexed = {r["specification_id"]: r for r in rows}
    entries = mapping.get("specifications", [])
    _need(isinstance(entries, list) and all(isinstance(row, dict) for row in entries), "reported specifications must be objects")
    identifiers = [row.get("id") for row in entries]
    _need(all(isinstance(identifier, str) for identifier in identifiers) and len(identifiers) == len(set(identifiers))
          and set(identifiers) <= set(indexed), "reported specifications must be unique and registered")
    presented, sources = _presented_specifications(project, paper_id, rows)
    errors = [identifier + ": a presented empirical statistic or source-bound claim is missing from the reporting map"
              for identifier in sorted(presented - set(identifiers))]
    inputs = [{"path": mapping_path.relative_to(project).as_posix(), "sha256": sha(mapping_path)}, *sources]
    for item in entries:
        actual = indexed[item["id"]]
        fields = set()
        for location in item.get("locations", []):
            field = location.get("field")
            _need(field in FIELDS or field == "phase", "unknown empirical reporting field")
            relative = location.get("path", "")
            _need(any(relative.startswith(f"papers/{paper_id}/{part}/") for part in ("manuscript", "tables", "figures", "supplement")), "reporting location must be final material for this paper")
            target = path_in(project, relative)
            _need(location.get("sha256") == sha(target), "empirical reporting source is stale")
            _need(isinstance(location.get("locator"), str) and re.fullmatch(r"L[1-9][0-9]*(?:-L?[1-9][0-9]*)?", location["locator"]), "use exact bounded source-line locations")
            bounds = [int(v) for v in re.findall(r"[0-9]+", location["locator"])]
            start, end = bounds[0], bounds[-1]
            lines = target.read_text(encoding="utf-8").splitlines()
            _need(1 <= start <= end <= len(lines), "empirical reporting lines are outside the actual source")
            quote = location.get("quote")
            _need(isinstance(quote, str) and quote.strip() and "\n".join(lines[start-1:end]).count(quote) == 1, "reporting quote must occur at its actual source lines")
            value = actual[field]
            from scripts.statistical_reporting import display_value
            _need(type(location.get("decimals", 6)) is int and 0 <= location.get("decimals", 6) <= 12, "bounded reporting precision required")
            notation = location.get("notation", "fixed")
            _need(notation in {"fixed", "scientific"}, "explicit fixed or scientific notation required")
            display = (format(value, "." + str(location.get("decimals", 6)) + "e")
                       if notation == "scientific" and type(value) in (int, float)
                       else display_value(value, location.get("decimals", 6)))
            if isinstance(value, str):
                other = "confirmatory" if display == "exploratory" else "exploratory"
                _need(re.search(r"\b" + re.escape(display) + r"\b", quote) is not None
                      and re.search(r"\b" + other + r"\b", quote) is None,
                      "reported analysis phase differs from actual run")
            else:
                _need(re.search(r"(?<![\w.\d+-])" + re.escape(display) + r"(?![\w.\d])", quote) is not None, "reported number differs from actual estimator output")
                _need(not (field in {"p_value", "p_adjusted"} and value > 0 and float(display) == 0), "do not round a positive p-value to zero")
            fields.add(field)
            inputs.append({"path": relative, "sha256": sha(target)})
        if set(FIELDS) | {"phase"} != fields:
            errors.append(item["id"] + ": map every estimate, uncertainty, p-value, sample count and analysis phase")
    return errors, inputs, identifiers


def _archive(project, paper_id, result, *, create=False):
    """Keep every registered result and specification outside manuscript exports."""
    from scripts.experiment_evidence import comparison_archive
    full = {key: result[key] for key in ("schema_version", "paper_id", "design_sha256", "registered_specifications", "diagnostics", "rows")}
    report = comparison_archive(project, paper_id, full, create=create)
    table = path_in(project, str(Path(report["path"]).with_name("empirical-estimates-" + report["sha256"] + ".csv")), exists=False)
    payload = table_bytes(result["rows"])
    if create and not table.exists():
        table.write_bytes(payload)
        record(project, [table], MODULE)
    _need(table.is_file() and table.read_bytes() == payload, "complete empirical table archive is missing or changed")
    return {"report": report, "table": {"path": table.relative_to(project).as_posix(), "sha256": sha(table)}}


@paper_scoped
def audit(project: Path, paper_id: str, *, require_mapping=False):
    _need(re.fullmatch(r"P[0-9]{2}", paper_id), "explicit paper ID required")
    result = {"schema_version": "1.0", "paper_id": paper_id, "status": "blocked", "errors": [], "rows": [],
              "reported_specification_ids": [], "full_manuscript_semantic_coverage_verified": False,
              "implementation_sha256": sha(Path(__file__)), "scientific_validity_verified": False,
              "scientific_completion_verified": False, "paid_calls": 0}
    try:
        card = read(path_in(project, f"papers/{paper_id}/empirical-design.json"))
        result["design_sha256"] = sha(project/f"papers/{paper_id}/empirical-design.json")
        result["registered_specifications"] = card["specifications"]
        result["diagnostics"] = _diagnostics(project, paper_id, card)
        for spec in card["specifications"]:
            measured_result = measured(project, paper_id, spec["id"])
            output = measured_result["result"]
            result["rows"].append({"specification_id": spec["id"], "method": spec["method"], "phase": spec["phase"],
                "family": spec["family"], **{k: output[k] for k in FIELDS if k not in {"ci_low", "ci_high", "p_adjusted"}},
                "ci_low": output["confidence_interval"][0], "ci_high": output["confidence_interval"][1],
                "source": measured_result["source"], "executor": measured_result["executor"]})
        # Separate confirmatory and exploratory families; never select the best p.
        for key in {(r["family"], r["phase"]) for r in result["rows"]}:
            family = sorted([r for r in result["rows"] if (r["family"], r["phase"]) == key], key=lambda r: r["p_value"])
            adjusted = 0.0
            for rank, row in enumerate(family):
                adjusted = min(1.0, max(adjusted, row["p_value"] * (len(family)-rank)))
                row["p_adjusted"] = adjusted
        mapping_errors, inputs, identifiers = _map_errors(project, paper_id, result["rows"], require_mapping=require_mapping)
        result["errors"].extend(mapping_errors)
        result["reporting_inputs"] = inputs
        result["reported_specification_ids"] = identifiers
        result["status"] = "blocked" if result["errors"] else "ready_for_scientific_review"
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, ImportError) as exc:
        result["errors"].append(str(exc))
    return result


@paper_scoped
def refresh(project, paper_id, *, require_mapping=False):
    result = audit(project, paper_id, require_mapping=require_mapping)
    outputs = []
    if result["rows"] and len(result["rows"]) == len(result.get("registered_specifications", [])):
        result["complete_results_archive"] = _archive(project, paper_id, result, create=True)
    if not result["errors"]:
        table = path_in(project, f"papers/{paper_id}/tables/empirical-estimates.csv", exists=False)
        selected = [row for row in result["rows"] if row["specification_id"] in result["reported_specification_ids"]]
        payload = table_bytes(selected) if selected else None
        if table.is_file() and table.read_bytes() != payload:
            prior = path_in(project, f"experiments/archive/{paper_id}/empirical-estimates-{sha(table)}.csv", exists=False)
            if not prior.exists():prior.write_bytes(table.read_bytes())
            _need(prior.read_bytes() == table.read_bytes(), "prior empirical table archive changed")
            outputs.append(prior)
        if selected:
            table.parent.mkdir(parents=True, exist_ok=True)
            table.write_bytes(payload)
            outputs.append(table)
        elif table.is_file():
            table.unlink()
    target = path_in(project, f"reports/empirical-reporting/{paper_id}.json", exists=False)
    write(target, result)
    record(project, [target, *outputs], MODULE)
    return result


@paper_scoped
def validate_saved_report(project, paper_id, *, require_mapping=False):
    expected = audit(project, paper_id, require_mapping=require_mapping)
    errors = list(expected["errors"])
    if expected["rows"] and len(expected["rows"]) == len(expected.get("registered_specifications", [])):
        try:expected["complete_results_archive"] = _archive(project, paper_id, expected)
        except (OSError, ValueError):errors.append("complete empirical archive is missing or changed")
    target = project/f"reports/empirical-reporting/{paper_id}.json"
    if not target.is_file() or read(target) != expected:
        errors.append("empirical reporting is missing or stale")
    table = project/f"papers/{paper_id}/tables/empirical-estimates.csv"
    selected = [row for row in expected["rows"] if row["specification_id"] in expected["reported_specification_ids"]]
    if not errors and ((selected and (not table.is_file() or table.read_bytes() != table_bytes(selected)))
                       or (not selected and table.exists())):
        errors.append("empirical result table differs from current sealed estimates")
    return errors
