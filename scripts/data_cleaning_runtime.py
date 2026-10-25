"""Standalone offline cleaning command for an already approved cloud run.

Copy this file unchanged into the experiment project and declare it, the
contract and every contract source as frozen inputs. The native runner verifies
G3 and the exact command before launching this process. No plan/state import,
network access, model call, automatic sample selection or scientific approval.
"""
from __future__ import annotations

import argparse
import copy
import csv
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import io
import json
import os
from pathlib import Path
import re


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _safe(root, relative, *, exists=True):
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("use project-relative runtime paths")
    candidate = Path(relative); target = root/candidate
    if (candidate.is_absolute() or ".." in candidate.parts or any(p.is_symlink() for p in (target, *target.parents))
            or not target.resolve().is_relative_to(root.resolve()) or exists and not target.is_file()):
        raise ValueError("escaped, symlinked or unavailable runtime path")
    return target


def _read(path):
    if path.stat().st_size > 64_000_000: raise ValueError("source exceeds bounded cleaning size")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError("JSON object required")
    return value


def _binding(root, binding):
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError("exact path/hash source binding required")
    target = _safe(root, binding["path"])
    if target.stat().st_size > 64_000_000 or _sha(target) != binding["sha256"]:
        raise ValueError("cleaning source hash changed or source is too large")
    return dict(binding)


def _number(value):
    if len(str(value)) > 128: raise ValueError("numeric value too long")
    try: number = Decimal(str(value))
    except InvalidOperation as exc: raise ValueError("finite numeric value required") from exc
    if not number.is_finite() or abs(number.adjusted()) > 100: raise ValueError("bounded finite numeric value required")
    return number


def _check(rows, definitions):
    from datetime import date
    summary = {}
    for name, definition in definitions.items():
        missing = 0
        for row in rows:
            value = row[name]
            if value in definition["missing_codes"]:
                missing += 1
                continue
            kind = definition["type"]
            if kind in {"integer", "number"}:
                number = _number(value)
                if kind == "integer" and number != number.to_integral_value(): raise ValueError("noninteger column value")
            elif kind == "date" and date.fromisoformat(value).isoformat() != value: raise ValueError("noncanonical date")
            elif kind == "boolean" and value not in {"0", "1", "true", "false"}: raise ValueError("invalid boolean column value")
        if missing and definition["required"]: raise ValueError("required cleaning input/output contains missing data")
        summary[name] = {"type": definition["type"], "unit": definition["unit"], "missing": missing, "invalid": 0}
    return summary


def transform(fields, rows, variables, steps):
    definitions = {item["name"]: copy.deepcopy(item) for item in variables}
    if len(definitions) != len(variables) or set(definitions) != set(fields): raise ValueError("dictionary needs every unique column")
    for item in definitions.values():
        if (set(item) != {"name", "type", "definition", "unit", "source_field", "formula", "missing_codes", "required"}
                or item["type"] not in {"string", "number", "integer", "date", "boolean"} or type(item["required"]) is not bool
                or any(not isinstance(item[key], str) or not item[key].strip() for key in ("definition", "unit", "source_field", "formula"))
                or not isinstance(item["missing_codes"], list) or "" not in item["missing_codes"]
                or any(not isinstance(value, str) for value in item["missing_codes"])):
            raise ValueError("explicit variable meanings/types/units/missing codes required")
    _check(rows, definitions)
    if not isinstance(steps, list) or len(steps) > 100: raise ValueError("bounded declared cleaning steps required")
    fields, rows, history, seen = list(fields), copy.deepcopy(rows), [], set()
    for step in steps:
        if (not isinstance(step, dict) or not isinstance(step.get("id"), str) or not step["id"].strip() or step["id"] in seen
                or not isinstance(step.get("reason"), str) or not step["reason"].strip()):
            raise ValueError("unique cleaning step ID and reason required")
        seen.add(step["id"])
        op, column = step.get("operation"), step.get("column")
        if column not in definitions: raise ValueError("cleaning column is absent")
        base = {"id", "reason", "operation", "column"}; before = len(rows); changed = 0
        if op == "rename":
            if set(step) != base|{"to"} or not isinstance(step["to"], str) or not step["to"].strip() or step["to"] in definitions:
                raise ValueError("rename needs an unused explicit target")
            fields[fields.index(column)] = step["to"]
            for row in rows: row[step["to"]] = row.pop(column)
            definitions[step["to"]] = definitions.pop(column); definitions[step["to"]]["name"] = step["to"]
            changed = len(rows)
        elif op == "normalize_missing":
            if set(step) != base: raise ValueError("missing normalization has unexpected fields")
            for row in rows:
                if row[column] in definitions[column]["missing_codes"] and row[column] != "": row[column] = ""; changed += 1
            definitions[column]["formula"] = "normalize_missing(" + definitions[column]["formula"] + ", codes=" + json.dumps(definitions[column]["missing_codes"]) + ")"
        elif op == "linear_unit_conversion":
            if (set(step) != base|{"from_unit", "to_unit", "factor", "offset"} or definitions[column]["unit"] != step["from_unit"]
                    or definitions[column]["type"] not in {"number", "integer"} or not isinstance(step["to_unit"], str) or not step["to_unit"].strip()
                    or _number(step["factor"]) == 0): raise ValueError("unit conversion needs matching numeric source unit and explicit nonzero factor")
            _number(step["offset"])
            for row in rows:
                if row[column] not in definitions[column]["missing_codes"]:
                    with localcontext() as context:
                        context.prec = 512
                        value = _number(row[column])*_number(step["factor"])+_number(step["offset"])
                    _number(value); row[column] = format(value, "f"); changed += 1
            definitions[column].update(unit=step["to_unit"], type="number",
                formula="("+definitions[column]["formula"]+") * "+str(step["factor"])+" + "+str(step["offset"]))
        elif op == "exclude_values":
            if (set(step) != base|{"values"} or not isinstance(step["values"], list) or not 1 <= len(step["values"]) <= 100
                    or any(not isinstance(value, str) for value in step["values"])): raise ValueError("exclusion needs explicit bounded values")
            rows = [row for row in rows if row[column] not in step["values"]]; changed = before-len(rows)
        else: raise ValueError("unsupported cleaning operation; no arbitrary code or automatic trimming")
        history.append({"id": step["id"], "operation": op, "reason": step["reason"], "rows_before": before,
            "rows_after": len(rows), "rows_changed_or_excluded": changed})
    if not rows: raise ValueError("cleaning excluded every row")
    return fields, rows, definitions, history, _check(rows, definitions)


def execute(root, contract_path, dataset_id, output, receipt):
    root = Path(root)
    run_id = os.environ.get("RESEARCH_OS_RUN_ID")
    if not run_id: raise ValueError("cleaning requires its already approved cloud executor run")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", dataset_id) or contract_path != f"data/contracts/{dataset_id}.json":
        raise ValueError("exact canonical data contract required")
    contract_file = _safe(root, contract_path); contract = _read(contract_file)
    if (contract.get("schema_version") != "1.0" or contract.get("dataset_id") != dataset_id
            or contract.get("cleaning_runtime_sha256") != _sha(Path(__file__))):
        raise ValueError("data contract identity or reviewed cleaning runtime hash differs")
    inputs = [{"path": contract_path, "sha256": _sha(contract_file)}]
    manifest = _binding(root, contract["manifest"]); source = _binding(root, contract["input"])
    if manifest["path"] != f"data/manifests/{dataset_id}.json": raise ValueError("canonical manifest required")
    if not source["path"].startswith("data/") or not source["path"].endswith(".csv"): raise ValueError("bounded data CSV source required")
    declared = _read(_safe(root, manifest["path"]))
    registry_file = _safe(root, "data/datasets.jsonl")
    if registry_file.stat().st_size > 64_000_000: raise ValueError("dataset registry exceeds bounded size")
    registered = [json.loads(line) for line in registry_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(not isinstance(item, dict) for item in registered): raise ValueError("dataset registry entries must be objects")
    matches = [item for item in registered if item.get("dataset_id") == dataset_id]
    if (len(matches) != 1 or matches[0] != declared or declared.get("dataset_id") != dataset_id
            or declared.get("download", {}).get("sha256") != source["sha256"]):
        raise ValueError("original CSV, canonical manifest and registered dataset must agree")
    inputs.extend([manifest, source, {"path": "data/datasets.jsonl", "sha256": _sha(registry_file)}])
    for join in contract.get("joins", []): inputs.append(_binding(root, join["right"]))
    if (not output.startswith("data/processed/") or not output.endswith(".csv")
            or not receipt.startswith("reports/data-cleaning/") or not receipt.endswith(".json")
            or output in {item["path"] for item in inputs} or receipt in {item["path"] for item in inputs}):
        raise ValueError("new processed CSV and cleaning receipt must be disjoint from all inputs")
    target, receipt_file = _safe(root, output, exists=False), _safe(root, receipt, exists=False)
    with _safe(root, source["path"]).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle); fields, rows = reader.fieldnames, []
        if not fields or len(fields) != len(set(fields)) or any(not field.strip() for field in fields): raise ValueError("unique CSV headers required")
        for row in reader:
            if len(rows) >= 1_000_000 or None in row or any(value is None for value in row.values()): raise ValueError("malformed or oversized CSV")
            rows.append(row)
    if not rows: raise ValueError("cleaning input has no rows")
    before = len(rows)
    fields, cleaned, definitions, history, summary = transform(fields, rows, contract["variables"], contract["cleaning_steps"])
    stream = io.StringIO(newline=""); writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader(); writer.writerows(cleaned); payload = stream.getvalue().encode("utf-8")
    result = {"schema_version": "1.0", "dataset_id": dataset_id, "run_id": run_id, "inputs": inputs,
        "implementation_sha256": _sha(Path(__file__)), "controller_implementation_sha256": contract.get("cleaning_implementation_sha256"),
        "output": {"path": output, "sha256": hashlib.sha256(payload).hexdigest()}, "rows_before": before,
        "rows_after": len(cleaned), "steps": history, "columns": summary, "output_dictionary": list(definitions.values()),
        "raw_input_unchanged": True, "scientific_validity_verified": False, "data_rights_verified": False, "gate_approved": False}
    for binding in inputs: _binding(root, binding)
    receipt_bytes = (json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+"\n").encode("utf-8")
    for path, content in ((target, payload), (receipt_file, receipt_bytes)):
        if path.exists() and path.read_bytes() != content: raise ValueError("refusing to overwrite a different generated cleaning artifact")
    target.parent.mkdir(parents=True, exist_ok=True); receipt_file.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload); receipt_file.write_bytes(receipt_bytes)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True); parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--output", required=True); parser.add_argument("--receipt", required=True)
    args = parser.parse_args()
    execute(Path.cwd(), args.contract, args.dataset_id, args.output, args.receipt)


if __name__ == "__main__": main()
