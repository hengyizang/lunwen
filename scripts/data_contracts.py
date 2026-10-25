"""Variable dictionaries, bounded CSV diagnostics and approved cleaning steps.

Audits read data without changing it. Cleaning is a deterministic experiment
command and reuses the current G3-approved runner contract; it grants no access,
approval, sample-selection authority or scientific certification.
"""
from __future__ import annotations

import argparse
import copy
import csv
from collections import Counter
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import io
import json
import os
from pathlib import Path
import re

from scripts.research_artifacts import path_in, read, record, sha, write

MAX_BYTES = 64_000_000
MAX_ROWS = 1_000_000
TYPES = {"string", "integer", "number", "date", "boolean"}


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", value):
        raise ValueError("bounded dataset ID required")
    return value


def _text(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise ValueError(name + " needs bounded nonempty text")
    return value


def _keys(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError("unexpected or missing fields: " + ", ".join(sorted(required)))


def _binding(project, value):
    _keys(value, {"path", "sha256"})
    target = path_in(project, value["path"])
    if target.stat().st_size > MAX_BYTES or value["sha256"] != sha(target):
        raise ValueError("source hash changed or source exceeds the bounded scan")
    return {"path": value["path"], "sha256": value["sha256"]}


def _csv(project, binding):
    source = _binding(project, binding)
    with path_in(project, source["path"]).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        if not fields or any(not field.strip() for field in fields) or len(fields) != len(set(fields)):
            raise ValueError("CSV needs unique nonempty header fields")
        rows = []
        for row in reader:
            if len(rows) >= MAX_ROWS or None in row or any(v is None for v in row.values()):
                raise ValueError("CSV is malformed or exceeds complete-scan row limit")
            rows.append(row)
    if not rows:
        raise ValueError("CSV needs actual rows")
    return fields, rows


def _number(value):
    if len(str(value)) > 128:
        raise ValueError("numeric value is too long")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("invalid numeric value") from exc
    if not result.is_finite() or abs(result.adjusted()) > 100:
        raise ValueError("numeric value must be finite and bounded")
    return result


def _variables(value, fields):
    if not isinstance(value, list) or len(value) != len(fields):
        raise ValueError("dictionary must cover every input column exactly")
    result = {}
    for item in value:
        _keys(item, {"name", "type", "definition", "unit", "source_field", "formula", "missing_codes", "required"})
        name = _text(item["name"], "variable name")
        if name not in fields or name in result or item["type"] not in TYPES or type(item["required"]) is not bool:
            raise ValueError("variable name/type/required declaration is invalid")
        for field in ("definition", "unit", "source_field", "formula"):
            _text(item[field], "variable " + field)
        missing = item["missing_codes"]
        if (not isinstance(missing, list) or len(missing) > 30 or any(not isinstance(x, str) for x in missing)
                or len(missing) != len(set(missing)) or "" not in missing):
            raise ValueError("explicit unique missing codes including empty string required")
        result[name] = copy.deepcopy(item)
    return result


def _column_summary(rows, variables, errors):
    from datetime import date
    summary = {}
    for name, spec in variables.items():
        missing, invalid = 0, 0
        for row in rows:
            value = row[name]
            if value in spec["missing_codes"]:
                missing += 1
                continue
            try:
                if spec["type"] in {"integer", "number"}:
                    number = _number(value)
                    if spec["type"] == "integer" and number != number.to_integral_value():
                        raise ValueError("noninteger")
                elif spec["type"] == "date":
                    if date.fromisoformat(value).isoformat() != value:
                        raise ValueError("noncanonical date")
                elif spec["type"] == "boolean" and value not in {"0", "1", "true", "false"}:
                    raise ValueError("noncanonical boolean")
            except (ValueError, InvalidOperation):
                invalid += 1
        if invalid:
            errors.append(f"{name}: {invalid} invalid/non-finite values for declared type")
        if missing and spec["required"]:
            errors.append(f"{name}: {missing} missing values in required column")
        summary[name] = {"type": spec["type"], "unit": spec["unit"], "missing": missing, "invalid": invalid}
    return summary


def _panel(rows, spec, variables, errors, warnings):
    _keys(spec, {"unit_columns", "time_column", "expected_times", "balance_policy"}, {"treatment"})
    units, time, calendar = spec["unit_columns"], spec["time_column"], spec["expected_times"]
    if (not isinstance(units, list) or not units or len(units) != len(set(units)) or time in units
            or any(x not in variables for x in units) or time not in variables):
        raise ValueError("panel needs distinct existing unit and time columns")
    if (not isinstance(calendar, list) or not 1 <= len(calendar) <= 10000
            or len(calendar) != len(set(calendar)) or any(not isinstance(x, str) or not x for x in calendar)):
        raise ValueError("panel needs the complete ordered expected calendar, including wholly absent periods")
    if spec["balance_policy"] not in {"require_balanced", "allow_unbalanced"}:
        raise ValueError("explicit panel balance policy required")
    observed, by_unit, by_time = Counter(), {}, Counter()
    blank, outside = 0, 0
    for row in rows:
        key, instant = tuple(row[x] for x in units), row[time]
        if any(row[x] in variables[x]["missing_codes"] for x in [*units, time]):
            blank += 1
        if instant not in calendar:
            outside += 1
        observed[(key, instant)] += 1
        by_unit.setdefault(key, {})[instant] = row
        by_time[instant] += 1
    duplicates = sum(count - 1 for count in observed.values())
    expected_cells = len(by_unit)*len(calendar)
    if expected_cells > 5_000_000:
        raise ValueError("declared panel exceeds the bounded five-million-cell audit")
    missing_count, missing_examples = 0, []
    for key in by_unit:
        for instant in calendar:
            if (key, instant) not in observed:
                missing_count += 1
                if len(missing_examples) < 30: missing_examples.append({"unit": list(key), "time": instant})
    if blank: errors.append(f"panel has {blank} blank/missing unit-time keys")
    if duplicates: errors.append(f"panel has {duplicates} duplicate unit-time keys")
    if outside: errors.append(f"panel has {outside} rows outside the declared calendar")
    if missing_count:
        (errors if spec["balance_policy"] == "require_balanced" else warnings).append(
            f"panel has {missing_count} missing unit-time cells; no deletion or imputation performed")
    report = {"units": len(by_unit), "observed_cells": len(observed), "expected_cells": expected_cells,
        "duplicate_keys": duplicates, "blank_keys": blank, "outside_calendar_rows": outside,
        "missing_cells": missing_count, "missing_examples": missing_examples,
        "wholly_absent_times": [instant for instant in calendar if instant not in by_time],
        "units_by_time": {instant: sum(instant in values for values in by_unit.values()) for instant in calendar},
        "entered_after_first_period": sum(calendar[0] not in values for values in by_unit.values()),
        "exited_before_last_period": sum(calendar[-1] not in values for values in by_unit.values()),
        "singletons": sum(len(values) == 1 for values in by_unit.values()), "balance_policy": spec["balance_policy"]}
    if "treatment" in spec:
        t = spec["treatment"]
        _keys(t, {"column", "untreated_values", "treated_values", "absorbing", "minimum_pre_periods", "minimum_post_periods"})
        if (t["column"] not in variables or type(t["absorbing"]) is not bool
                or any(type(t[x]) is not int or t[x] < 0 for x in ("minimum_pre_periods", "minimum_post_periods"))):
            raise ValueError("invalid treatment timing declaration")
        for state in ("untreated_values", "treated_values"):
            if not isinstance(t[state], list) or not t[state] or any(not isinstance(x, str) for x in t[state]):
                raise ValueError("explicit treatment codes required")
        if set(t["untreated_values"]) & set(t["treated_values"]):
            raise ValueError("treatment codes overlap")
        reversals, insufficient, unknown = 0, 0, 0
        for values in by_unit.values():
            sequence = [values[instant][t["column"]] for instant in calendar if instant in values]
            if any(v not in t["untreated_values"] + t["treated_values"] for v in sequence): unknown += 1
            treated = [i for i, value in enumerate(sequence) if value in t["treated_values"]]
            if treated:
                first = treated[0]
                reversals += any(value in t["untreated_values"] for value in sequence[first:])
                insufficient += first < t["minimum_pre_periods"] or len(sequence)-first < t["minimum_post_periods"]
        if unknown: errors.append(f"treatment timing has unknown/missing states for {unknown} units")
        if insufficient: errors.append(f"treatment timing lacks declared pre/post observations for {insufficient} units")
        if reversals and t["absorbing"]: errors.append(f"treatment reverses for {reversals} units despite absorbing declaration")
        report["treatment_timing"] = {"reversals": reversals, "insufficient_pre_post_units": insufficient, "unknown_state_units": unknown,
            "causal_identification_verified": False}
    return report


def _joins(project, rows, joins, variables, errors):
    if not isinstance(joins, list) or len(joins) > 20:
        raise ValueError("bounded join declarations required")
    results, bindings, seen = [], [], set()
    for join in joins:
        _keys(join, {"id", "right", "left_keys", "right_keys", "right_key_units", "right_key_missing_codes", "cardinality", "minimum_match_rate", "reason"})
        identifier = _text(join["id"], "join ID")
        if identifier in seen: raise ValueError("duplicate join ID")
        seen.add(identifier); _text(join["reason"], "join reason")
        binding = _binding(project, join["right"]); fields, right_rows = _csv(project, binding)
        left_keys, right_keys = join["left_keys"], join["right_keys"]
        if (not isinstance(left_keys, list) or not isinstance(right_keys, list) or not left_keys or len(left_keys) != len(right_keys)
                or len(set(left_keys)) != len(left_keys) or len(set(right_keys)) != len(right_keys)
                or any(key not in variables for key in left_keys) or any(key not in fields for key in right_keys)
                or join["cardinality"] not in {"one_to_one", "many_to_one"}):
            raise ValueError("join keys and one_to_one/many_to_one cardinality must be explicit")
        if not isinstance(join["right_key_units"], dict) or set(join["right_key_units"]) != set(right_keys):
            raise ValueError("right join-key units must be explicit")
        if any(variables[left]["unit"] != join["right_key_units"][right] for left, right in zip(left_keys, right_keys)):
            raise ValueError("join-key units differ; convert explicitly before joining")
        missing_codes = join["right_key_missing_codes"]
        if (not isinstance(missing_codes, dict) or set(missing_codes) != set(right_keys)
                or any(not isinstance(codes, list) or "" not in codes or any(not isinstance(code, str) for code in codes)
                       for codes in missing_codes.values())):
            raise ValueError("right join-key missing codes including empty string must be explicit")
        threshold = _number(join["minimum_match_rate"])
        if not 0 <= threshold <= 1: raise ValueError("join match threshold must be between zero and one")
        left = [tuple(row[key] for key in left_keys) for row in rows]
        right = [tuple(row[key] for key in right_keys) for row in right_rows]
        if (any(row[key] in variables[key]["missing_codes"] or not row[key].strip() for row in rows for key in left_keys)
                or any(row[key] in missing_codes[key] or not row[key].strip() for row in right_rows for key in right_keys)):
            errors.append(identifier + ": blank/missing join keys")
        if len(set(right)) != len(right): errors.append(identifier + ": right keys violate declared cardinality")
        if join["cardinality"] == "one_to_one" and len(set(left)) != len(left): errors.append(identifier + ": left keys violate one_to_one cardinality")
        right_set = set(right)
        matched = sum(key in right_set for key in left)
        rate = Decimal(matched)/Decimal(len(left))
        if rate < threshold: errors.append(identifier + ": join match rate is below the declared threshold")
        results.append({"id": identifier, "left_rows": len(left), "right_rows": len(right), "matched_left_rows": matched,
            "unmatched_left_rows": len(left)-matched, "match_rate": str(rate), "cardinality": join["cardinality"], "join_executed": False})
        bindings.append(binding)
    return results, bindings


def _clean_plan(steps, variables):
    if not isinstance(steps, list) or len(steps) > 100:
        raise ValueError("bounded cleaning steps required")
    current, seen = copy.deepcopy(variables), set()
    for step in steps:
        if not isinstance(step, dict): raise ValueError("cleaning step must be an object")
        _text(step.get("id"), "cleaning step ID"); _text(step.get("reason"), "cleaning step reason")
        if step["id"] in seen: raise ValueError("duplicate cleaning step ID")
        seen.add(step["id"]); op = step.get("operation")
        if op == "rename":
            _keys(step, {"id", "reason", "operation", "column", "to"})
            if step["column"] not in current or not isinstance(step["to"], str) or not step["to"].strip() or step["to"] in current:
                raise ValueError("rename needs an existing column and unused target")
            current[step["to"]] = current.pop(step["column"]); current[step["to"]]["name"] = step["to"]
        elif op == "normalize_missing":
            _keys(step, {"id", "reason", "operation", "column"})
            if step["column"] not in current: raise ValueError("missing normalization column is absent")
        elif op == "linear_unit_conversion":
            _keys(step, {"id", "reason", "operation", "column", "from_unit", "to_unit", "factor", "offset"})
            if (step["column"] not in current or current[step["column"]]["type"] not in {"integer", "number"}
                    or current[step["column"]]["unit"] != step["from_unit"] or _number(step["factor"]) == 0):
                raise ValueError("unit conversion needs a matching source unit, numeric column and nonzero factor")
            _number(step["offset"]); _text(step["to_unit"], "target unit")
            current[step["column"]].update(unit=step["to_unit"], type="number")
        elif op == "exclude_values":
            _keys(step, {"id", "reason", "operation", "column", "values"})
            if (step["column"] not in current or not isinstance(step["values"], list) or not step["values"]
                    or len(step["values"]) > 100 or any(not isinstance(x, str) for x in step["values"])):
                raise ValueError("row exclusion needs an existing column and explicit bounded values")
        else:
            raise ValueError("unsupported cleaning operation; arbitrary code and automatic outlier trimming are forbidden")
    return current


def _load(project, dataset_id):
    dataset_id = _id(dataset_id)
    relative = f"data/contracts/{dataset_id}.json"; contract = read(path_in(project, relative))
    _keys(contract, {"schema_version", "dataset_id", "manifest", "input", "variables", "joins", "cleaning_steps"}, {"panel", "cleaning_implementation_sha256", "cleaning_runtime_sha256"})
    if contract["schema_version"] != "1.0" or contract["dataset_id"] != dataset_id:
        raise ValueError("data contract identity differs from requested dataset")
    if contract["cleaning_steps"] and contract.get("cleaning_implementation_sha256") != sha(Path(__file__)):
        raise ValueError("cleaning implementation must be hash-bound in the frozen contract")
    if contract["cleaning_steps"] and contract.get("cleaning_runtime_sha256") != sha(Path(__file__).with_name("data_cleaning_runtime.py")):
        raise ValueError("standalone cleaning runtime must be hash-bound in the frozen contract")
    manifest = _binding(project, contract["manifest"])
    if manifest["path"] != f"data/manifests/{dataset_id}.json": raise ValueError("use the dataset's canonical manifest")
    declared = read(path_in(project, manifest["path"]))
    registry = path_in(project, "data/datasets.jsonl")
    registered = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(not isinstance(item, dict) for item in registered): raise ValueError("dataset registry entries must be objects")
    matches = [item for item in registered if item.get("dataset_id") == dataset_id]
    if len(matches) != 1 or matches[0] != declared or declared.get("dataset_id") != dataset_id:
        raise ValueError("canonical manifest and registered dataset must match exactly")
    source = _binding(project, contract["input"])
    if declared.get("download", {}).get("sha256") != source["sha256"]:
        raise ValueError("input CSV must match the registered original download hash; derived data uses the cleaning output dictionary")
    if not source["path"].startswith("data/") or Path(source["path"]).suffix.lower() != ".csv":
        raise ValueError("data contract input must be a CSV in data/")
    fields, rows = _csv(project, source); variables = _variables(contract["variables"], fields)
    return contract, fields, rows, variables, [{"path": relative, "sha256": sha(project/relative)}, manifest, source,
        {"path": "data/datasets.jsonl", "sha256": sha(registry)}]


def audit(project: Path, dataset_id: str) -> dict:
    """Read-only complete-scan audit; a pass never grants data rights or G3."""
    try:
        contract, fields, rows, variables, bindings = _load(project, dataset_id)
        errors, warnings = [], []
        columns = _column_summary(rows, variables, errors)
        panel = _panel(rows, contract["panel"], variables, errors, warnings) if "panel" in contract else None
        joins, join_bindings = _joins(project, rows, contract["joins"], variables, errors)
        _clean_plan(contract["cleaning_steps"], variables)
        return {"schema_version": "1.0", "dataset_id": dataset_id, "pass": not errors, "errors": errors,
            "warnings": warnings, "inputs": bindings+join_bindings, "implementation_sha256": sha(Path(__file__)),
            "rows": len(rows), "columns": columns, "panel": panel, "joins": joins,
            "cleaning_steps_declared": len(contract["cleaning_steps"]), "data_mutated": False,
            "complete_scan": True, "scientific_validity_verified": False, "data_rights_verified": False, "gate_approved": False}
    except (OSError, ValueError, TypeError, KeyError, csv.Error, UnicodeError) as exc:
        return {"schema_version": "1.0", "dataset_id": dataset_id, "pass": False, "errors": [str(exc)],
            "warnings": [], "complete_scan": False, "data_mutated": False, "scientific_validity_verified": False,
            "data_rights_verified": False, "gate_approved": False, "implementation_sha256": sha(Path(__file__))}


def refresh(project: Path, dataset_id: str) -> dict:
    result = audit(project, _id(dataset_id)); target = project/f"reports/data-contracts/{dataset_id}.json"
    write(target, result); record(project, [target], "scripts/data_contracts.py")
    return result


def validate_saved_report(project: Path, dataset_id: str) -> list[str]:
    target = project/f"reports/data-contracts/{_id(dataset_id)}.json"
    if not target.is_file(): return ["current variable-level data contract audit is missing"]
    from scripts.output_provenance import current_origin
    origin = current_origin(project, target)
    if origin.get("status") != "tracked" or origin.get("provider") != "deterministic-control-plane":
        return ["data contract report provenance is stale or untrusted"]
    current = audit(project, dataset_id)
    return current["errors"] + (["data contract report is stale"] if read(target) != current else [])


def _clean_rows(fields, rows, variables, steps):
    """Pure bounded transform for approved execution and cloud fixture tests."""
    _clean_plan(steps, variables)
    fields, rows, definitions = list(fields), copy.deepcopy(rows), copy.deepcopy(variables)
    history = []
    for step in steps:
        before = len(rows); op, column = step["operation"], step["column"]
        changed = 0
        if op == "rename":
            fields[fields.index(column)] = step["to"]
            for row in rows: row[step["to"]] = row.pop(column)
            definitions[step["to"]] = definitions.pop(column); definitions[step["to"]]["name"] = step["to"]
            changed = len(rows)
        elif op == "normalize_missing":
            for row in rows:
                if row[column] in definitions[column]["missing_codes"] and row[column] != "":
                    row[column] = ""; changed += 1
            definitions[column]["formula"] = "normalize_missing(" + definitions[column]["formula"] + ", codes=" + json.dumps(definitions[column]["missing_codes"]) + ")"
        elif op == "linear_unit_conversion":
            for row in rows:
                if row[column] not in definitions[column]["missing_codes"]:
                    with localcontext() as context:
                        context.prec = 512
                        converted = _number(row[column]) * _number(step["factor"]) + _number(step["offset"])
                    _number(converted); row[column] = format(converted, "f"); changed += 1
            definitions[column].update(unit=step["to_unit"], type="number",
                formula="("+definitions[column]["formula"]+") * "+str(step["factor"])+" + "+str(step["offset"]))
        elif op == "exclude_values":
            rows = [row for row in rows if row[column] not in step["values"]]; changed = before-len(rows)
        history.append({"id": step["id"], "operation": op, "reason": step["reason"], "rows_before": before,
            "rows_after": len(rows), "rows_changed_or_excluded": changed})
    if not rows: raise ValueError("cleaning excluded every row")
    return fields, rows, definitions, history


def _preview(project, dataset_id):
    result = audit(project, dataset_id)
    if not result["pass"]: raise ValueError("data contract failed: " + "; ".join(result["errors"]))
    contract, fields, rows, variables, _ = _load(project, dataset_id)
    fields, cleaned, definitions, history = _clean_rows(fields, rows, variables, contract["cleaning_steps"])
    errors = []; summary = _column_summary(cleaned, definitions, errors)
    if errors: raise ValueError("preparation produced invalid data: " + "; ".join(errors))
    stream = io.StringIO(newline=""); writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader(); writer.writerows(cleaned); payload = stream.getvalue().encode("utf-8")
    report = {"schema_version": "1.0", "dataset_id": dataset_id, "purpose": "data_preparation_only",
        "inputs": result["inputs"], "implementation_sha256": sha(Path(__file__)),
        "output": {"path": f"data/processed-preview/{dataset_id}.csv", "sha256": hashlib.sha256(payload).hexdigest()},
        "rows_before": len(rows), "rows_after": len(cleaned), "steps": history,
        "columns": summary, "output_dictionary": list(definitions.values()), "preparation_contract": contract,
        "raw_input_unchanged": True, "experiment_executed": False, "scientific_validity_verified": False,
        "data_rights_verified": False, "gate_approved": False}
    for binding in result["inputs"]: _binding(project, binding)
    return payload, report


def preview_cleaning(project: Path, dataset_id: str) -> dict:
    """Deterministic open-G3 preparation, never estimation or an experiment."""
    if os.environ.get("GITHUB_ACTIONS") != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1":
        raise ValueError("data preparation requires the cloud control plane")
    state = read(path_in(project, "state/run.json"))
    if state.get("stage") != "experiment-design" or state.get("gate") != "G3" or state.get("status") != "awaiting_work":
        raise ValueError("data preparation requires the open G3 experiment-design stage")
    registry = path_in(project, "experiments/registry.jsonl", exists=False)
    if registry.is_file() and registry.read_text(encoding="utf-8").strip():
        raise ValueError("data preparation cannot change a dataset after experimental attempts")
    if any(read(path).get("status") == "frozen" for path in (project/"papers").glob("P[0-9][0-9]/preregistration.json")):
        raise ValueError("data preparation must precede frozen preregistration")
    payload, report = _preview(project, _id(dataset_id))
    target = path_in(project, report["output"]["path"], exists=False)
    receipt = path_in(project, f"reports/data-cleaning/preview-{dataset_id}.json", exists=False)
    outputs = []
    if receipt.is_file() and read(receipt) != report:
        # Preserve the earlier recipe, source hashes and sample-flow record.
        archive = path_in(project, f"reports/data-cleaning/preparation-history/{dataset_id}/{sha(receipt)}.json", exists=False)
        if archive.exists() and archive.read_bytes() != receipt.read_bytes(): raise ValueError("preparation history changed")
        archive.parent.mkdir(parents=True, exist_ok=True); archive.write_bytes(receipt.read_bytes()); outputs.append(archive)
    target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(payload)
    write(receipt, report); record(project, [*outputs, target, receipt], "scripts/data_contracts.py")
    return report


def validate_preview(project: Path, dataset_id: str) -> list[str]:
    """Replay preparation after freezing without changing any source or output."""
    try:
        payload, expected = _preview(project, _id(dataset_id))
        receipt = path_in(project, f"reports/data-cleaning/preview-{dataset_id}.json")
        target = path_in(project, expected["output"]["path"])
        from scripts.output_provenance import current_origin
        if any(current_origin(project, path).get("status") != "tracked"
               or current_origin(project, path).get("provider") != "deterministic-control-plane" for path in (receipt, target)):
            return ["prepared data provenance is stale or untrusted"]
        if read(receipt) != expected or target.read_bytes() != payload: return ["prepared data or preparation report is stale"]
        return []
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, csv.Error) as exc:
        return [str(exc)]


def clean(project: Path, dataset_id: str, output: str, receipt: str) -> dict:
    """Execute only as the exact already approved experiment-run command."""
    run_id = os.environ.get("RESEARCH_OS_RUN_ID")
    if not run_id: raise ValueError("cleaning requires the approved experiment runner")
    from scripts.experiment_runner import approved_plan
    plan, _ = approved_plan(project, project/"experiments/plan.json", project/"experiments/budget.json")
    runs = [run for run in plan["runs"] if run["run_id"] == run_id]
    if len(runs) != 1 or set(runs[0]["expected_outputs"]) != {output, receipt}:
        raise ValueError("cleaning outputs differ from the exact approved run")
    if not output.startswith("data/processed/") or not output.endswith(".csv") or not receipt.startswith("reports/data-cleaning/") or not receipt.endswith(".json"):
        raise ValueError("cleaning outputs must use data/processed CSV and reports/data-cleaning JSON")
    target, log_path = path_in(project, output, exists=False), path_in(project, receipt, exists=False)
    result = audit(project, dataset_id)
    if not result["pass"]: raise ValueError("data contract failed: " + "; ".join(result["errors"]))
    contract, fields, rows, variables, bindings = _load(project, dataset_id)
    if contract.get("cleaning_implementation_sha256") != sha(Path(__file__)):
        raise ValueError("cleaning implementation must be hash-bound in the frozen contract")
    all_bindings = result["inputs"]
    declared = {(item["path"], item["sha256"]) for item in runs[0]["inputs"]}
    if any((item["path"], item["sha256"]) not in declared for item in all_bindings):
        raise ValueError("every data contract source must be declared in the approved run inputs")
    if output in {item["path"] for item in all_bindings} or receipt in {item["path"] for item in all_bindings}:
        raise ValueError("raw input and cleaning outputs must be disjoint")
    fields, cleaned, definitions, history = _clean_rows(fields, rows, variables, contract["cleaning_steps"])
    errors = []; summary = _column_summary(cleaned, definitions, errors)
    if errors: raise ValueError("cleaning produced invalid data: " + "; ".join(errors))
    handle = io.StringIO(newline=""); writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
    writer.writeheader(); writer.writerows(cleaned); payload = handle.getvalue().encode("utf-8")
    report = {"schema_version": "1.0", "dataset_id": dataset_id, "run_id": run_id, "inputs": all_bindings,
        "implementation_sha256": sha(Path(__file__)), "output": {"path": output, "sha256": hashlib.sha256(payload).hexdigest()},
        "rows_before": len(rows), "rows_after": len(cleaned), "steps": history, "columns": summary,
        "output_dictionary": list(definitions.values()), "raw_input_unchanged": True, "scientific_validity_verified": False,
        "data_rights_verified": False, "gate_approved": False}
    # Re-read every source after processing and before publishing either output.
    for binding in all_bindings: _binding(project, binding)
    log_bytes = (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")
    for path, content in ((target, payload), (log_path, log_bytes)):
        if path.exists() and path.read_bytes() != content:
            raise ValueError("refusing to overwrite a different generated cleaning artifact")
    target.parent.mkdir(parents=True, exist_ok=True); log_path.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload); log_path.write_bytes(log_bytes)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["audit", "clean", "preview"])
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--output"); parser.add_argument("--receipt")
    args = parser.parse_args()
    if args.operation == "clean":
        if not args.output or not args.receipt: parser.error("clean requires --output and --receipt")
        clean(args.project_root, args.dataset_id, args.output, args.receipt)
    elif args.operation == "preview":
        print(json.dumps(preview_cleaning(args.project_root, args.dataset_id), indent=2))
    else:
        value = refresh(args.project_root, args.dataset_id)
        print(json.dumps(value, indent=2)); return 0 if value["pass"] else 2
    return 0


if __name__ == "__main__": raise SystemExit(main())
