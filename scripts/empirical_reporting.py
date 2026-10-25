"""Sealed empirical estimates, complete tables and source-located manuscript checks.

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


def measured(project: Path, paper_id: str, specification_id: str) -> dict:
    from scripts import empirical_design, empirical_runtime
    from scripts.figure_lineage import run_seal
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


def _diagnostics(project, paper_id, card):
    from scripts.figure_lineage import run_seal
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


def _map_errors(project, paper_id, rows, *, require_mapping):
    mapping_path = project/f"papers/{paper_id}/empirical-reporting-map.json"
    if not mapping_path.is_file():
        return (["empirical manuscript reporting map is required"] if require_mapping else []), []
    mapping = read(mapping_path)
    _need(mapping.get("paper_id") == paper_id and mapping.get("schema_version") == "1.0", "invalid empirical reporting map identity")
    indexed = {r["specification_id"]: r for r in rows}
    entries = mapping.get("specifications", [])
    _need(isinstance(entries, list) and len(entries) == len(indexed)
          and {r.get("id") for r in entries} == set(indexed), "report every registered specification, including adverse/exploratory results")
    errors, inputs = [], [{"path": mapping_path.relative_to(project).as_posix(), "sha256": sha(mapping_path)}]
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
    return errors, inputs


def audit(project: Path, paper_id: str, *, require_mapping=False):
    _need(re.fullmatch(r"P[0-9]{2}", paper_id), "explicit paper ID required")
    result = {"schema_version": "1.0", "paper_id": paper_id, "status": "blocked", "errors": [], "rows": [],
              "implementation_sha256": sha(Path(__file__)), "scientific_validity_verified": False,
              "scientific_completion_verified": False, "paid_calls": 0}
    try:
        card = read(path_in(project, f"papers/{paper_id}/empirical-design.json"))
        result["design_sha256"] = sha(project/f"papers/{paper_id}/empirical-design.json")
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
        mapping_errors, inputs = _map_errors(project, paper_id, result["rows"], require_mapping=require_mapping)
        result["errors"].extend(mapping_errors)
        result["reporting_inputs"] = inputs
        result["status"] = "blocked" if result["errors"] else "ready_for_scientific_review"
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, ImportError) as exc:
        result["errors"].append(str(exc))
    return result


def refresh(project, paper_id, *, require_mapping=False):
    result = audit(project, paper_id, require_mapping=require_mapping)
    outputs = []
    if not result["errors"]:
        table = path_in(project, f"papers/{paper_id}/tables/empirical-estimates.csv", exists=False)
        table.parent.mkdir(parents=True, exist_ok=True)
        table.write_bytes(table_bytes(result["rows"]))
        outputs.append(table)
    target = path_in(project, f"reports/empirical-reporting/{paper_id}.json", exists=False)
    write(target, result)
    record(project, [target, *outputs], MODULE)
    return result


def validate_saved_report(project, paper_id, *, require_mapping=False):
    expected = audit(project, paper_id, require_mapping=require_mapping)
    errors = list(expected["errors"])
    target = project/f"reports/empirical-reporting/{paper_id}.json"
    if not target.is_file() or read(target) != expected:
        errors.append("empirical reporting is missing or stale")
    table = project/f"papers/{paper_id}/tables/empirical-estimates.csv"
    if not errors and (not table.is_file() or table.read_bytes() != table_bytes(expected["rows"])):
        errors.append("empirical result table differs from current sealed estimates")
    return errors
